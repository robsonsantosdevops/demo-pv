"""Cria User Defined Fields (UDFs) na tabela ORDR (Sales Order header) do SAP B1.

Idempotente: se o UDF já existir (ValidValuesMDCollection já contém a chave),
o SAP devolve 400 com mensagem clara e o script pula. Tipos suportados:
- Alpha (string com Size)
- Memo (texto longo)
- Numeric (inteiro)

Uso:
    python scripts/sap_create_order_udfs.py                 # cria todos
    python scripts/sap_create_order_udfs.py --dry-run       # só imprime os payloads
    python scripts/sap_create_order_udfs.py --only U_Curso_Nome

Após criar UDFs, a próxima chamada a POST /Orders aceita a chave `U_<Name>`
no payload. O GET de Orders passa a retornar os campos UDF junto com os
standard. Não precisa de restart do Service Layer na v2 moderna.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from dotenv import load_dotenv  # noqa: E402

from middleware.integrations.sap import (  # noqa: E402
    SapClient,
    SapSession,
    load_sap_config,
)

TABLE = "ORDR"  # Sales Order header

# Especificação dos UDFs. Cada um vira U_<Name> na entidade Order.
UDFS: list[dict] = [
    {"name": "SF_OppId",           "descr": "Salesforce Opportunity Id",        "type": "db_Alpha",   "size": 18},
    {"name": "SF_OppName",         "descr": "Salesforce Opportunity Name",      "type": "db_Alpha",   "size": 100},
    {"name": "SF_CorrelationId",   "descr": "Correlation ID (jornada)",         "type": "db_Alpha",   "size": 80},
    {"name": "Pedido_Id",          "descr": "Id do pedido no checkout",         "type": "db_Numeric"},
    {"name": "Aluno_Nome",         "descr": "Nome do aluno",                     "type": "db_Alpha",   "size": 100},
    {"name": "Aluno_Email",        "descr": "Email do aluno",                    "type": "db_Alpha",   "size": 100},
    {"name": "Curso_Nome",         "descr": "Nome do curso (primeiro item)",    "type": "db_Alpha",   "size": 200},
    {"name": "Curso_Descricao",    "descr": "Descrição do curso (memo)",         "type": "db_Memo",    "edit_size": 2000},
]


def _build_payload(spec: dict) -> dict:
    body = {
        "TableName": TABLE,
        "Name": spec["name"],
        "Description": spec["descr"],
        "Type": spec["type"],
        "Mandatory": "tNO",
    }
    if spec["type"] == "db_Alpha":
        body["Size"] = spec["size"]
    elif spec["type"] == "db_Memo":
        body["EditSize"] = spec.get("edit_size", 2000)
    return body


def _create(client: SapClient, spec: dict) -> str:
    url = f"{client.config.base_url}/UserFieldsMD"
    payload = _build_payload(spec)
    try:
        r = client.post(url, payload)
        field_id = r.get("FieldID") or r.get("fieldID")
        return f"[ok]   U_{spec['name']:20s} -> FieldID={field_id}"
    except Exception as e:  # noqa: BLE001
        msg = str(e)
        if "already exists" in msg.lower() or "duplicate" in msg.lower() or "já existe" in msg.lower():
            return f"[skip] U_{spec['name']:20s} já existe"
        return f"[ERR]  U_{spec['name']:20s} {msg[:300]}"


def main() -> int:
    load_dotenv(dotenv_path=Path(".env"))

    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--only", nargs="*", help="Cria só estes (por nome U_xxx ou xxx).")
    args = p.parse_args()

    selected = UDFS
    if args.only:
        wanted = {n.removeprefix("U_") for n in args.only}
        selected = [s for s in UDFS if s["name"] in wanted]
        if not selected:
            print(f"nenhum UDF casou com {args.only}")
            return 2

    if args.dry_run:
        for spec in selected:
            print(f"\n>> U_{spec['name']}")
            print(json.dumps(_build_payload(spec), indent=2, ensure_ascii=False))
        return 0

    client = SapClient(load_sap_config(), SapSession())
    print(f"target table: {TABLE}")
    print(f"base: {client.config.base_url}")
    print(f"udfs to process: {len(selected)}\n")

    for spec in selected:
        print(_create(client, spec))

    return 0


if __name__ == "__main__":
    sys.exit(main())
