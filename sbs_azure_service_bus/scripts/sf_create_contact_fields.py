"""Cria campos custom no sObject Contact via Tooling API.

Idempotente: se o campo já existir, pula. Concede FLS (Read+Edit) no
PermissionSet shadow do profile do usuário autenticado.

Uso:
    python scripts/sf_create_contact_fields.py                # cria todos
    python scripts/sf_create_contact_fields.py --dry-run      # só imprime
    python scripts/sf_create_contact_fields.py --only Aluno_Id__c
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

OBJECT = "Contact"

FIELDS: list[dict] = [
    {"name": "Aluno_Id__c", "label": "Aluno ID", "type": "Number", "precision": 10, "scale": 0, "unique": True, "external_id": True},
    {"name": "CPF__c",      "label": "CPF",      "type": "Text",   "length": 14},
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
    else:
        raise ValueError(f"tipo não suportado: {t}")
    return meta


def _create_field(client: SalesforceClient, spec: dict) -> str:
    full_name = f"{OBJECT}.{spec['name']}"
    payload = {"FullName": full_name, "Metadata": _build_metadata(spec)}
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
    p.add_argument("--only", nargs="*")
    p.add_argument("--skip-fls", action="store_true")
    p.add_argument("--fls-only", action="store_true")
    args = p.parse_args()

    selected = FIELDS
    if args.only:
        wanted = set(args.only)
        selected = [f for f in FIELDS if f["name"] in wanted]
        if not selected:
            print(f"nenhum field casou com {args.only}")
            return 2

    if args.dry_run:
        for spec in selected:
            print(f"\n>> {OBJECT}.{spec['name']}")
            print(json.dumps(_build_metadata(spec), indent=2, ensure_ascii=False))
        return 0

    client = SalesforceClient(load_salesforce_config())
    client.authenticate()
    print(f"connected: {client.instance_url}")
    print(f"target: {OBJECT}\nfields: {len(selected)}\n")

    if not args.fls_only:
        for spec in selected:
            print(_create_field(client, spec))

    if not args.skip_fls:
        print("\n=== FLS ===")
        try:
            parent_id = _current_user_profile_permission_set(client)
            print(f"PermissionSet: {parent_id}")
        except Exception as e:  # noqa: BLE001
            print(f"[ERR] {e}")
            return 0
        for spec in selected:
            print(_grant_fls(client, parent_id, OBJECT, spec["name"]))

    return 0


if __name__ == "__main__":
    sys.exit(main())
