"""Troca TODOS os telefones de clientes por números fictícios, nos dados da Mora e do CRM.

Feito para gravar demonstração sem expor o número de quem testou. Sem argumento nenhum:

1. lê os telefones cadastrados (`leads.telefone` e `clientes.telefone` da Mora, `leads.phone_e164`
   do CRM) e os que aparecem FORMATADOS em qualquer texto (mensagens, cartão, notas do CRM);
2. sorteia um fictício para cada um, mantendo o DDD e o tamanho, sem repetir nem colidir;
3. procura cada número, em qualquer formato (+55 11 98765-4321, (11) 98765-4321, 5511987654321,
   98765-4321…), em todas as colunas de texto, JSON e binárias dos bancos `sdr` e `crm` — inclusive
   as mensagens e o checkpoint do LangGraph, que guarda a conversa em msgpack — e troca só os
   DÍGITOS, mantendo a pontuação. O tamanho não muda: o JSON continua válido, o E.164 do CRM passa
   no CHECK e o msgpack continua legível.

O mesmo número real vira o MESMO fictício em todas as tabelas, então o vínculo entre a Mora e o CRM
continua de pé. Telefone de corretor não é tocado: vem de `data/equipe/` e já é fictício.

Uso (de dentro de local/, com o compose no ar):

    docker compose exec -T agent python - < ../scripts/anonimizar_telefone.py            # só conta
    docker compose exec -T agent python - --aplicar < ../scripts/anonimizar_telefone.py  # grava
    docker compose exec -T agent python - --listar < ../scripts/anonimizar_telefone.py   # lista, mascarado

Nenhum número real é impresso. Cada banco é uma transação: se algo falhar, nada é gravado nele.
"""
import os
import random
import re
import sys

import psycopg

APLICAR = "--aplicar" in sys.argv
BANCOS = {
    "sdr": os.environ.get("SDR_DATABASE_DSN", "postgresql://sdr:sdr@db:5432/sdr"),
    "crm": os.environ.get("CRM_DATABASE_DSN", "postgresql://sdr:sdr@db:5432/crm"),
}
FONTES = {"sdr": [("leads", "telefone"), ("clientes", "telefone")], "crm": [("leads", "phone_e164")]}


def nacional(valor):
    """'+55 (11) 98765-4321' → '11987654321'; None se não parece telefone brasileiro."""
    d = re.sub(r"\D", "", valor or "")
    if d.startswith("55") and len(d) in (12, 13):
        d = d[2:]
    return d if len(d) in (10, 11) and d[0] != "0" else None


DDD = {11, 12, 13, 14, 15, 16, 17, 18, 19, 21, 22, 24, 27, 28, 31, 32, 33, 34, 35, 37, 38, 41, 42, 43, 44,
       45, 46, 47, 48, 49, 51, 53, 54, 55, 61, 62, 63, 64, 65, 66, 67, 68, 69, 71, 73, 74, 75, 77, 79, 81,
       82, 83, 84, 85, 86, 87, 88, 89, 91, 92, 93, 94, 95, 96, 97, 98, 99}


def plausivel(n):
    """Número nacional com DDD que existe; celular com 9 na frente, fixo começando de 2 a 5."""
    return bool(n) and int(n[:2]) in DDD and ((len(n) == 11 and n[2] == "9") or (len(n) == 10 and n[2] in "2345"))


# Campos que SÃO identificadores: o chat do Telegram, a sessão do site, chaves. Trocar um dígito
# ali desliga o cliente do canal, então eles ficam de fora da coleta e da troca.
PROTEGIDAS = {("canais", "identificador")}


def protegida(tabela, coluna):
    return (tabela, coluna) in PROTEGIDAS or coluna == "id" or coluna.endswith("_id") or coluna.startswith("identificador")


# A chave pode estar em JSON ("chat_id": …), em texto (id=…) ou no msgpack do checkpoint, onde
# entre a chave e o valor só há bytes de tipo e tamanho (lidos como latin-1, caem em \x80-\xff).
CTX_ID = re.compile(r'(?i)(?:id|identificador|chat|thread|session|sessao|hash|token|key)[a-z_]*["\'\s:=\x80-\xff]{0,4}$')


def em_contexto_de_id(texto, inicio):
    """'"chat_id": 1234567890' — o número logo depois de uma chave de identificador não é telefone."""
    return bool(CTX_ID.search(texto[max(0, inicio - 24):inicio]))


def _colunas(conn, tabela):
    return {r[0] for r in conn.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=%s",
        (tabela,)).fetchall()}


# 1. os telefones reais
reais = set()
for banco, fontes in FONTES.items():
    with psycopg.connect(BANCOS[banco]) as conn:
        for tabela, coluna in fontes:
            if coluna in _colunas(conn, tabela):
                for (v,) in conn.execute(f'SELECT DISTINCT "{coluna}" FROM "{tabela}" WHERE "{coluna}" IS NOT NULL'):
                    n = nacional(v)
                    if n:
                        reais.add(n)
# Telefone que só aparece no texto (o cliente digitou, mas o número nunca foi para o cadastro).
# Aqui só vale o que tem CARA de telefone — com +55, parênteses, espaço ou hífen —, porque uma
# sequência crua de 10 ou 11 dígitos pode ser id do Telegram, protocolo ou preço.
RE_FORMATADO = re.compile(
    r"(?<![0-9A-Za-z_])(?:\+\s*55[\s().\-]*\(?[1-9][0-9]\)?[\s.\-]*9?[0-9]{4}[\s.\-]?[0-9]{4}"
    r"|\(?[1-9][0-9]\)?[\s.\-]+9?[0-9]{4}[\s.\-]?[0-9]{4}"
    r"|\([1-9][0-9]\)9?[0-9]{4}[\s.\-]?[0-9]{4}"
    r"|9[0-9]{4}-[0-9]{4})(?![0-9A-Za-z_])")
RE_CRU = re.compile(r"(?<![0-9A-Za-z_\-/.])\+?(?:55)?[1-9][0-9]{9,10}(?![0-9A-Za-z_\-/])")
avulsos = set()
for banco, dsn in BANCOS.items():
    with psycopg.connect(dsn) as conn:
        for tabela, coluna in conn.execute("""
                SELECT c.table_name, c.column_name FROM information_schema.columns c
                  JOIN information_schema.tables t USING (table_schema, table_name)
                 WHERE c.table_schema='public' AND t.table_type='BASE TABLE' AND c.is_generated='NEVER'
                   AND c.data_type IN ('text','character varying','jsonb','json') AND c.table_name <> 'corretores'
                """).fetchall():
            for (v,) in conn.execute(f'SELECT "{coluna}"::text FROM "{tabela}" WHERE "{coluna}"::text ~ %s',
                                     (r"\d{4}[\s.\-]?\d{4}",)):
                if protegida(tabela, coluna):
                    continue
                for m in RE_FORMATADO.finditer(v):
                    n = nacional(m.group(0))
                    if n:
                        reais.add(n)
                    elif re.fullmatch(r"9\d{4}-\d{4}", m.group(0)):
                        avulsos.add(m.group(0).replace("-", ""))
                for m in RE_CRU.finditer(v):
                    n = nacional(m.group(0))
                    if plausivel(n) and not em_contexto_de_id(v, m.start()):
                        reais.add(n)
# celular sem DDD que não bate com nenhum cadastrado: entra com o DDD 11, só para ter par
for a in avulsos:
    if not any(n.endswith(a) for n in reais):
        reais.add("11" + a)
if not reais:
    sys.exit("Nenhum telefone encontrado.")


def mascara(n):
    return f"({n[:2]}) {n[2]}****-**{n[-2:]}"


if "--listar" in sys.argv:
    for n in sorted(reais):
        print(mascara(n))
    print(f"{len(reais)} telefone(s).")
    sys.exit(0)

# 2. um fictício por número: mesmo DDD, mesmo tamanho, celular começando com 9
rnd = random.SystemRandom()
mapa, usados = {}, set(reais)
for n in sorted(reais):
    while True:
        f = n[:2] + ("9" if len(n) == 11 else rnd.choice("2345")) + "".join(rnd.choice("0123456789") for _ in range(len(n) - 3))
        if f not in usados:
            break
    mapa[n] = f
    usados.add(f)
por_assinante = {n[2:]: f[2:] for n, f in mapa.items() if len(n) == 11}

SEP = r"[\s.\-]?"
alternativas = []
for n in sorted(reais, key=len, reverse=True):
    ddd, ass = n[:2], n[2:]
    alternativas.append(r"(?:\+?\s*55[\s().\-]*)?\(?" + ddd[0] + ddd[1] + r"\)?[\s.\-]*" + SEP.join(ass))
for ass in sorted(por_assinante):                         # celular sem DDD, ainda inconfundível
    alternativas.append(SEP.join(ass))
RE_TXT = re.compile(r"(?<![0-9A-Za-z_])(?:" + "|".join(alternativas) + r")(?![0-9A-Za-z_])")
RE_BIN = re.compile(r"(?<![0-9A-Za-z_])(?:".encode() + "|".join(alternativas).encode() + r")(?![0-9A-Za-z_])".encode())


def _troca(trecho):
    dig = re.sub(r"\D", "", trecho)
    alvo = None
    for tam in (11, 10):
        if len(dig) >= tam and dig[-tam:] in mapa:
            alvo = mapa[dig[-tam:]]
            break
    if alvo is None:
        alvo = por_assinante.get(dig[-9:])
    if alvo is None:
        return trecho
    resto, out = list(alvo), list(trecho)
    for i in range(len(out) - 1, -1, -1):
        if not resto:
            break
        if out[i].isdigit():
            out[i] = resto.pop()
    return "".join(out)


# 3. a varredura
total = 0
for banco, dsn in BANCOS.items():
    with psycopg.connect(dsn) as conn:
        colunas = conn.execute("""
            SELECT c.table_name, c.column_name, c.data_type
              FROM information_schema.columns c
              JOIN information_schema.tables t USING (table_schema, table_name)
             WHERE c.table_schema = 'public' AND t.table_type = 'BASE TABLE'
               AND c.data_type IN ('text', 'character varying', 'jsonb', 'json', 'bytea')
               AND c.is_generated = 'NEVER'
               AND NOT (c.table_name = 'corretores')
             ORDER BY 1, 2""").fetchall()
        for tabela, coluna, tipo in colunas:
            if protegida(tabela, coluna):
                continue
            if tipo == "bytea":
                linhas = conn.execute(f'SELECT ctid, "{coluna}" FROM "{tabela}" WHERE "{coluna}" IS NOT NULL').fetchall()
            else:
                linhas = conn.execute(f'SELECT ctid, "{coluna}"::text FROM "{tabela}" WHERE "{coluna}"::text ~ %s',
                                      (r"\d{4}",)).fetchall()
            n = 0
            for ctid, valor in linhas:
                if tipo == "bytea":
                    antigo = bytes(valor)
                    novo = RE_BIN.sub(lambda m: m.group(0) if em_contexto_de_id(antigo[max(0, m.start() - 24):m.start()].decode("latin-1"), 24)
                                      else _troca(m.group(0).decode()).encode(), antigo)
                    cast = ""
                else:
                    antigo = valor
                    novo = RE_TXT.sub(lambda m: m.group(0) if em_contexto_de_id(antigo, m.start()) else _troca(m.group(0)), antigo)
                    cast = "::jsonb" if tipo == "jsonb" else "::json" if tipo == "json" else ""
                if novo == antigo:
                    continue
                if APLICAR:
                    conn.execute(f'UPDATE "{tabela}" SET "{coluna}" = %s{cast} WHERE ctid = %s', (novo, ctid))
                n += 1
            if n:
                print(f"{banco}.{tabela}.{coluna}: {n} linha(s)")
                total += n
        if not APLICAR:
            conn.rollback()

print(f"{len(reais)} telefone(s) encontrado(s). " + ("Trocado" if APLICAR else "Seria trocado") + f" em {total} linha(s).")
if not APLICAR and total:
    print("Rode de novo com --aplicar para gravar.")
