"""CLI do seed e do reset.

Reset **só existe aqui**, nunca em REST nem em MCP (seção 9). Três travas, e as três precisam
passar:

1. `APP_ENV` em `development` ou `test`;
2. o nome do banco contém "crm" e não é o de produção de ninguém — e todo registro existente
   precisa estar marcado como sintético;
3. `--confirm-reset` digitado à mão.

Parece exagero para um laboratório. Não é: um comando que apaga tabelas acaba, mais cedo ou mais
tarde, colado num terminal apontado para o lugar errado, e a única defesa que funciona é a que está
no caminho do comando.

    python -m sdr_crm.seed --seed 42 --reference-date 2026-09-17T12:00:00Z
    python -m sdr_crm.seed --reset --confirm-reset --seed 42
"""
import argparse
import json
import sys
from datetime import UTC, datetime

from ..config import get_settings
from ..db.connection import transacao
from .aplicar import aplicar
from .gerar import Plano

TABELAS = ("idempotency_records", "audit_events", "handoffs", "tasks", "visits",
           "availability_slots", "property_interests", "interactions", "preferences",
           "opportunities", "leads", "properties")


def _conferir_ambiente() -> None:
    cfg = get_settings()
    if not cfg.sintetico:
        raise SystemExit(f"Recuso: APP_ENV={cfg.app_env!r} não é ambiente sintético.")
    banco = cfg.database_dsn.rsplit("/", 1)[-1].split("?")[0]
    if "crm" not in banco:
        raise SystemExit(f"Recuso: banco {banco!r} não parece o banco do CRM.")


def _resetar(dataset_id: str) -> dict:
    """Apaga apenas o dataset indicado, em uma transação — e aborta se houver dado sem marca
    sintética. Um único registro real na base significa que este banco não é o que se pensava."""
    with transacao() as conn:
        reais = conn.execute(
            """SELECT (SELECT count(*) FROM leads WHERE NOT synthetic)
                    + (SELECT count(*) FROM properties WHERE NOT synthetic) AS n""").fetchone()
        if reais["n"]:
            raise SystemExit(f"Recuso: {reais['n']} registro(s) sem marca sintética neste banco.")
        apagados = {}
        for tabela in TABELAS:
            colunas = conn.execute(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = %s AND column_name = 'dataset_id'", (tabela,)).fetchone()
            if colunas:
                r = conn.execute(f"DELETE FROM {tabela} WHERE dataset_id = %s", (dataset_id,))
            else:
                r = conn.execute(f"DELETE FROM {tabela}")
            apagados[tabela] = r.rowcount
    return apagados


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="sdr_crm.seed", description="Massa sintética do CRM.")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--reference-date", default="2026-09-17T12:00:00Z",
                   help="Âncora temporal: tudo que é 'futuro' ou 'vencido' é relativo a ela.")
    p.add_argument("--dataset-id", default="padrao")
    p.add_argument("--reset", action="store_true", help="Apaga o dataset antes de aplicar.")
    p.add_argument("--confirm-reset", action="store_true", help="Obrigatório junto com --reset.")
    args = p.parse_args(argv)

    _conferir_ambiente()
    if args.reset and not args.confirm_reset:
        raise SystemExit("--reset exige --confirm-reset.")

    referencia = datetime.fromisoformat(args.reference_date.replace("Z", "+00:00"))
    if referencia.tzinfo is None:
        referencia = referencia.replace(tzinfo=UTC)

    if args.reset:
        print(json.dumps({"reset": _resetar(args.dataset_id)}, ensure_ascii=False))

    contagens = aplicar(Plano(seed=args.seed, referencia=referencia, dataset_id=args.dataset_id))
    print(json.dumps({"seed": args.seed, "reference_date": referencia.isoformat(),
                      "dataset_id": args.dataset_id, "contagens": contagens}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
