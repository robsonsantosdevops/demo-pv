"""Cria campos custom na Opportunity via Salesforce Tooling API.

Idempotente: se o campo já existir (DUPLICATE_VALUE), pula. Tipos suportados:
Text, Number, DateTime, Email, LongTextArea, Picklist.

Reutiliza credenciais do .env (SF_USERNAME, SF_PASSWORD, SF_SECURITY_TOKEN,
SF_DOMAIN, opcionalmente SF_CONSUMER_KEY/SECRET).

Uso:
    python scripts/sf_create_opportunity_fields.py                # cria todos
    python scripts/sf_create_opportunity_fields.py --dry-run      # só imprime o payload
    python scripts/sf_create_opportunity_fields.py --only Pedido_Id__c Parcelas__c
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from dotenv import load_dotenv  # noqa: E402

from middleware.integrations.salesforce import (  # noqa: E402
    SalesforceClient,
    load_salesforce_config,
)

OBJECT = "Opportunity"

# Especificação dos campos. Keys neutros; _build_metadata() traduz p/ JSON do Tooling API.
FIELDS: list[dict] = [
    {"name": "Correlation_Id__c",   "label": "Correlation ID",   "type": "Text",         "length": 80,  "unique": True, "external_id": True},
    {"name": "Pedido_Id__c",        "label": "Pedido ID",        "type": "Number",       "precision": 10, "scale": 0, "external_id": True},
    {"name": "Aluno_Id__c",         "label": "Aluno ID",         "type": "Number",       "precision": 10, "scale": 0, "external_id": True},
    {"name": "Aluno_Nome__c",       "label": "Aluno Nome",       "type": "Text",         "length": 100},
    {"name": "Aluno_Email__c",      "label": "Aluno Email",      "type": "Email"},
    {"name": "Parcelas__c",         "label": "Parcelas",         "type": "Number",       "precision": 3, "scale": 0},
    {"name": "Pedido_Created_At__c","label": "Pedido Created At","type": "DateTime"},
    {"name": "Status_Checkout__c",  "label": "Status Checkout",  "type": "Picklist",     "values": ["aguardando_pagamento", "pago", "cancelado", "estornado"]},
    {"name": "Itens_Json__c",       "label": "Itens (JSON)",     "type": "LongTextArea", "length": 32768, "visible_lines": 10},
    {"name": "Pagamento_Id__c",     "label": "Pagamento ID",     "type": "Number",       "precision": 10, "scale": 0, "external_id": True},
    {"name": "Pagamento_Protocolo__c","label": "Pagamento Protocolo","type": "Text",      "length": 60},
    {"name": "Forma_Pagamento__c",  "label": "Forma Pagamento",  "type": "Picklist",     "values": ["pix", "cartao_credito", "cartao_debito", "boleto"]},
    {"name": "Status_Pagamento__c", "label": "Status Pagamento", "type": "Picklist",     "values": ["aprovado", "recusado", "pendente", "estornado"]},
    {"name": "Status_Pedido__c",    "label": "Status Pedido",    "type": "Picklist",     "values": ["pago", "aguardando", "cancelado", "estornado"]},
    {"name": "Cartao_Final__c",     "label": "Cartão Final",     "type": "Text",         "length": 4},
    # Campos reservados — ficam vazios até o checkout passar a enviá-los.
    {"name": "Curso_Nome__c",       "label": "Curso - Nome",     "type": "Text",         "length": 200},
    {"name": "Curso_Descricao__c",  "label": "Curso - Descrição","type": "LongTextArea", "length": 32768, "visible_lines": 10},
]


def _build_metadata(spec: dict) -> dict:
    t = spec["type"]
    meta: dict = {"label": spec["label"], "type": t, "required": False}

    if t == "Text":
        meta["length"] = spec["length"]
        if spec.get("unique"):
            meta["unique"] = True
        if spec.get("external_id"):
            meta["externalId"] = True
    elif t == "Number":
        meta["precision"] = spec["precision"]
        meta["scale"] = spec.get("scale", 0)
        if spec.get("unique"):
            meta["unique"] = True
        if spec.get("external_id"):
            meta["externalId"] = True
    elif t == "DateTime":
        pass
    elif t == "Email":
        pass
    elif t == "LongTextArea":
        meta["length"] = spec.get("length", 32768)
        meta["visibleLines"] = spec.get("visible_lines", 10)
    elif t == "Picklist":
        meta["valueSet"] = {
            "restricted": False,
            "valueSetDefinition": {
                "sorted": False,
                "value": [
                    {"fullName": v, "default": False, "label": v}
                    for v in spec["values"]
                ],
            },
        }
    else:
        raise ValueError(f"tipo não suportado: {t}")

    return meta


def _create_field(client: SalesforceClient, spec: dict) -> str:
    full_name = f"{OBJECT}.{spec['name']}"
    payload = {"FullName": full_name, "Metadata": _build_metadata(spec)}

    # Tooling API: /services/data/vXX.X/tooling/sobjects/CustomField
    path = f"/services/data/{client.config.api_version}/tooling/sobjects/CustomField"
    try:
        result = client.post(path, payload)
        return f"[ok]   criado: {spec['name']} -> {result.get('id')}"
    except Exception as e:  # noqa: BLE001
        msg = str(e)
        if "DUPLICATE_VALUE" in msg or "already exists" in msg.lower() or "duplicate" in msg.lower():
            return f"[skip] já existe: {spec['name']}"
        return f"[ERR]  {spec['name']}: {msg[:300]}"


def _current_user_profile_permission_set(client: SalesforceClient) -> str:
    """Retorna o Id do PermissionSet associado ao profile do user autenticado.

    Cada Profile no SF tem um PermissionSet "shadow" com `IsOwnedByProfile=true`.
    É nele que adicionamos FieldPermissions para conceder FLS via Data API.
    """
    username = client.config.username.replace("'", "\\'")
    user_rec = client.query(f"SELECT Id, ProfileId FROM User WHERE Username = '{username}' LIMIT 1")
    if not user_rec:
        raise RuntimeError(f"Usuário {client.config.username!r} não encontrado")
    profile_id = user_rec[0]["ProfileId"]
    ps = client.query(
        "SELECT Id FROM PermissionSet "
        f"WHERE IsOwnedByProfile = true AND ProfileId = '{profile_id}' LIMIT 1"
    )
    if not ps:
        raise RuntimeError(f"PermissionSet shadow do profile {profile_id} não encontrado")
    return ps[0]["Id"]


def _grant_fls(client: SalesforceClient, parent_id: str, sobject: str, field: str) -> str:
    """Concede Read+Edit no campo via FieldPermissions. Idempotente."""
    payload = {
        "ParentId": parent_id,
        "Field": f"{sobject}.{field}",
        "SobjectType": sobject,
        "PermissionsRead": True,
        "PermissionsEdit": True,
    }
    try:
        client.post("/sobjects/FieldPermissions/", payload)
        return f"[ok]   fls: {field}"
    except Exception as e:  # noqa: BLE001
        msg = str(e)
        if "DUPLICATE_VALUE" in msg or "duplicate" in msg.lower():
            return f"[skip] fls já concedida: {field}"
        return f"[ERR]  fls {field}: {msg[:250]}"


def main() -> int:
    load_dotenv(dotenv_path=Path(".env"))

    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--only", nargs="*", help="Criar só estes campos (por nome API).")
    p.add_argument("--skip-fls", action="store_true", help="Pular concessão de FLS no profile do user.")
    p.add_argument("--fls-only", action="store_true", help="Só conceder FLS (não tenta criar campos).")
    args = p.parse_args()

    selected = FIELDS
    if args.only:
        wanted = set(args.only)
        selected = [f for f in FIELDS if f["name"] in wanted]
        if not selected:
            print(f"nenhum field casou com {args.only}; disponíveis: {[f['name'] for f in FIELDS]}")
            return 2

    if args.dry_run:
        for spec in selected:
            full = f"{OBJECT}.{spec['name']}"
            print(f"\n>> {full}")
            print(json.dumps(_build_metadata(spec), indent=2, ensure_ascii=False))
        return 0

    client = SalesforceClient(load_salesforce_config())
    client.authenticate()
    print(f"connected: {client.instance_url}")
    print(f"api: {client.config.api_version}")
    print(f"target object: {OBJECT}")
    print(f"fields to process: {len(selected)}\n")

    if not args.fls_only:
        for spec in selected:
            print(_create_field(client, spec))

    if not args.skip_fls:
        print("\n=== concedendo FLS (Read+Edit) no profile do user autenticado ===")
        try:
            parent_id = _current_user_profile_permission_set(client)
            print(f"PermissionSet shadow do profile: {parent_id}")
        except Exception as e:  # noqa: BLE001
            print(f"[ERR] não foi possível descobrir o PermissionSet: {e}")
            return 0
        for spec in selected:
            print(_grant_fls(client, parent_id, OBJECT, spec["name"]))

    return 0


if __name__ == "__main__":
    sys.exit(main())
