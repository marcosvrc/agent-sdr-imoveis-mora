"""Semeia a equipe de corretores da Mora (tabela `corretores`), para testar com uma equipe de verdade.

Uso:
    python scripts/semear_corretores.py                 # 20 corretores, idempotente
    python scripts/semear_corretores.py --vincular-crm  # tenta casar com `users` do CRM por e-mail
    python scripts/semear_corretores.py --listar         # só mostra o que existe hoje

Até aqui o cadastro nascia vazio de propósito — quem usava o projeto criava dois corretores pela
tela e seguia. Com vinte, dá para ver o que só aparece em escala: distribuição por região no
encaminhamento, agenda concorrida, paginação da lista, carteira ao desligar alguém.

**Pessoas fictícias, e nada além disso.** Os nomes são inventados; os e-mails usam `example.com`,
reservado pela RFC 2606 justamente para exemplos; os telefones seguem a convenção de número falso
já usada nos testes (`5511999990000`), que não é faixa reservada — é convenção do projeto, e não
deve ser lida como número de alguém. **Não há campo CRECI em lugar nenhum do sistema, e este script
não inventa um**: registro profissional é credencial, e credencial fabricada num sistema que fala
com cliente é outra categoria de problema. No site, o CRECI aparece como placeholder marcado
(`apps/web/src/lib/imobiliaria.ts`).

Sem foto, também de propósito: o painel desenha o avatar com as iniciais quando `foto` é nulo
(`Avatar` em `apps/dashboard/src/components/ui.tsx`), e retrato de pessoa inventada seria ou foto de
alguém real usada indevidamente, ou rosto sintético passando por corretor.
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "shared"))

from sdr_shared.db.painel import CorretorRepository       # noqa: E402
from sdr_shared.models import Corretor                    # noqa: E402

# A equipe vem de data/equipe/corretores.json, e não de uma lista aqui dentro: o seed do CRM lê o
# MESMO arquivo para criar os `users`, e é o e-mail que liga os dois lados. Duas listas, uma em cada
# serviço, descreveriam a mesma imobiliária com pessoas diferentes — e o encaminhamento não
# encontraria ninguém do outro lado. É o mesmo motivo do acervo estar num arquivo só.
EQUIPE_JSON = Path(__file__).resolve().parents[1] / "data/equipe/corretores.json"


def equipe() -> list[dict]:
    return json.loads(EQUIPE_JSON.read_text(encoding="utf-8"))


def _vinculos_do_crm() -> dict[str, str]:
    """`{email: users.id}` do CRM, quando o banco estiver alcançável.

    Casar por e-mail é o que dá: o `users.id` do CRM é um uuid5 determinístico calculado lá, e
    reimplementá-lo aqui criaria duas fontes para o mesmo id. Sem CRM, `crm_user_id` fica vazio —
    que é o estado documentado de "ponte desligada": o encaminhamento sobe sem destinatário e o CRM
    atribui a quem aceitar.
    """
    dsn = os.getenv("CRM_DATABASE_DSN") or os.getenv("CRM_TEST_DSN")
    if not dsn:
        print("… --vincular-crm sem CRM_DATABASE_DSN: seguindo sem vínculo")
        return {}
    try:
        import psycopg
        from psycopg.rows import dict_row
        with psycopg.connect(dsn, row_factory=dict_row) as c:
            rows = c.execute("SELECT id, email FROM users").fetchall()
    except Exception as e:                                   # noqa: BLE001 - seed não derruba por isto
        print(f"… CRM inalcançável ({type(e).__name__}): seguindo sem vínculo")
        return {}
    return {str(r["email"]).lower(): str(r["id"]) for r in rows}


def main(vincular_crm: bool = False, listar: bool = False) -> None:
    repo = CorretorRepository()
    if listar:
        for c in repo.listar():
            print(f"{c.id:28} {c.nome:22} {'ativo' if c.ativo else 'inativo':8} {','.join(c.regioes)}")
        print(f"{len(repo.listar())} corretor(es)")
        return

    vinculos = _vinculos_do_crm() if vincular_crm else {}
    pessoas = equipe()
    novos = ligados = 0
    for pessoa in pessoas:
        existente = repo.get(pessoa["id"])
        # Vínculo já existente não é perdido quando o CRM está fora do ar: sem isto, rodar o seed
        # sem `--vincular-crm` desligaria a ponte de toda a equipe sem ninguém pedir.
        crm_user_id = (vinculos.get(pessoa["email"].lower())
                       or (existente.crm_user_id if existente else None))
        ligados += bool(crm_user_id)
        novos += not existente
        repo.upsert(Corretor(id=pessoa["id"], nome=pessoa["nome"], email=pessoa["email"],
                             telefone=pessoa["telefone"], regioes=pessoa["regioes"],
                             ativo=pessoa["ativo"], foto=None, crm_user_id=crm_user_id))
    inativos = sum(1 for x in pessoas if not x["ativo"])
    total = len(repo.listar())
    print(f"✓ {len(pessoas)} corretores semeados ({novos} novo(s)); {total} no cadastro; "
          f"{inativos} inativo(s); {ligados} com vínculo no CRM")
    if vincular_crm and not ligados:
        print("  (nenhum e-mail casou com `users` do CRM — rode `make crm-seed` antes)")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Semeia os corretores da Mora (idempotente).")
    p.add_argument("--vincular-crm", action="store_true",
                   help="casa os corretores com os usuários do CRM pelo e-mail")
    p.add_argument("--listar", action="store_true", help="apenas lista o cadastro atual")
    a = p.parse_args()
    main(a.vincular_crm, a.listar)
