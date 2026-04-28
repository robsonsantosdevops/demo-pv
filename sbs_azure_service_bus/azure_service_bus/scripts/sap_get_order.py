"""Consulta Orders no SAP B1 Service Layer.

Uso:
    # Últimas N orders
    python scripts/sap_get_order.py --recent 10

    # Últimas N filtrando CardCode
    python scripts/sap_get_order.py --by-cardcode C40000 --recent 5

    # Por DocEntry (um ou vários)
    python scripts/sap_get_order.py 41336
    python scripts/sap_get_order.py 41330 41332 41334 41336

    # Pelo opportunity_id do Salesforce (NumAtCard)
    python scripts/sap_get_order.py --opp-id 006g5000003PNEDAA4

    # Pelo correlation_id da jornada (U_SF_CorrelationId)
    python scripts/sap_get_order.py --correlation-id jornada-8-98bb04e1-94ca-474f-a5da-b4f67f577062

    # JSON cru (todos os campos, inclusive UDFs completos)
    python scripts/sap_get_order.py --recent 3 --raw

Usa o mesmo sessionId / SAP_BASE_URL / SAP_COMPANY_DB do middleware.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from dotenv import load_dotenv  # noqa: E402

from middleware.integrations.sap import SapClient, SapSession, load_sap_config  # noqa: E402


def _odata_escape(s: str) -> str:
    return s.replace("'", "''")


def _format_order(o: dict) -> str:
    lines = o.get("DocumentLines") or []
    line_strs = [
        f"    - line#{ln.get('LineNum')} ItemCode={ln.get('ItemCode')} "
        f"Qty={ln.get('Quantity')} UnitPrice={ln.get('UnitPrice')} "
        f"Total={ln.get('LineTotal')}"
        for ln in lines
    ]
    # UDFs começam com U_ no JSON da Order
    udfs = sorted(k for k in o if k.startswith("U_"))
    udf_strs = []
    for k in udfs:
        v = o.get(k)
        if v in (None, ""):
            continue  # oculta UDFs vazios pra não poluir
        if isinstance(v, str) and len(v) > 110:
            v = v[:110] + "…"
        udf_strs.append(f"    {k:24s} = {v!r}")
    return (
        f"  DocEntry:  {o.get('DocEntry')}\n"
        f"  DocNum:    {o.get('DocNum')}\n"
        f"  DocDate:   {o.get('DocDate')}\n"
        f"  DocDueDate:{o.get('DocDueDate')}\n"
        f"  CardCode:  {o.get('CardCode')}\n"
        f"  NumAtCard: {o.get('NumAtCard')!r}\n"
        f"  DocTotal:  {o.get('DocTotal')}\n"
        f"  DocStatus: {o.get('DocumentStatus')}\n"
        f"  Comments:\n    {(o.get('Comments') or '').replace(chr(10), chr(10) + '    ')}\n"
        f"  UDFs:\n" + ("\n".join(udf_strs) if udf_strs else "    (nenhum)") + "\n"
        f"  Lines ({len(lines)}):\n" + ("\n".join(line_strs) if line_strs else "    (vazio)")
    )


def _print(orders: list[dict], raw: bool) -> None:
    for o in orders:
        print("---")
        if raw:
            print(json.dumps(o, ensure_ascii=False, indent=2))
        else:
            print(_format_order(o))


def main() -> int:
    load_dotenv()

    p = argparse.ArgumentParser()
    p.add_argument("doc_entries", nargs="*", type=int, help="DocEntry(s) a consultar.")
    p.add_argument("--recent", type=int, default=0, help="Puxa as N orders mais recentes.")
    p.add_argument("--by-cardcode", default=None, help="Filtra por CardCode.")
    p.add_argument("--opp-id", default=None, help="Filtra por NumAtCard (opportunity_id do SF).")
    p.add_argument("--correlation-id", default=None, help="Filtra por U_SF_CorrelationId.")
    p.add_argument("--raw", action="store_true", help="Imprime JSON cru em vez de resumo.")
    args = p.parse_args()

    used_filters = sum([
        bool(args.doc_entries),
        args.recent > 0,
        bool(args.opp_id),
        bool(args.correlation_id),
    ])
    if used_filters == 0:
        p.error("passe DocEntries, --recent N, --opp-id X ou --correlation-id X")

    client = SapClient(load_sap_config(), SapSession())

    # --recent (com ou sem --by-cardcode)
    if args.recent > 0:
        filter_clause = ""
        if args.by_cardcode:
            filter_clause = f"&$filter=CardCode eq '{_odata_escape(args.by_cardcode)}'"
        url = (
            f"{client.config.base_url}/Orders"
            f"?$orderby=DocEntry desc&$top={args.recent}{filter_clause}"
        )
        resp = client.get(url)
        orders = resp.get("value", [])
        print(f"\n=== últimas {len(orders)} Order(s) ===")
        _print(orders, args.raw)
        return 0

    # --opp-id / --correlation-id (filtros por convenção do middleware)
    if args.opp_id or args.correlation_id:
        if args.opp_id:
            clause = f"NumAtCard eq '{_odata_escape(args.opp_id)}'"
            label = f"opp-id={args.opp_id}"
        else:
            clause = f"U_SF_CorrelationId eq '{_odata_escape(args.correlation_id)}'"
            label = f"correlation-id={args.correlation_id}"
        url = f"{client.config.base_url}/Orders?$filter={clause}&$orderby=DocEntry desc&$top=20"
        resp = client.get(url)
        orders = resp.get("value", [])
        print(f"\n=== Orders com {label}: {len(orders)} ===")
        _print(orders, args.raw)
        return 0

    # Por DocEntry explícito
    for de in args.doc_entries:
        url = f"{client.config.base_url}/Orders({de})"
        try:
            o = client.get(url)
        except Exception as e:  # noqa: BLE001
            print(f"--- DocEntry {de}: ERRO {e}")
            continue
        print("---")
        if args.raw:
            print(json.dumps(o, ensure_ascii=False, indent=2))
        else:
            print(_format_order(o))
    return 0


if __name__ == "__main__":
    sys.exit(main())
