"""Peek mensagens de filas (principal) ou DLQs do namespace.

Uso:
    python scripts/receive.py                     # todas as filas (main) do namespace
    python scripts/receive.py pedidos             # só a fila 'pedidos' (main)
    python scripts/receive.py oportunidades       # só a fila 'oportunidades' (main)

    python scripts/receive.py dlq                 # todas as DLQs do namespace
    python scripts/receive.py dlq pedidos         # só a DLQ de 'pedidos'
    python scripts/receive.py dlq oportunidades   # só a DLQ de 'oportunidades'

    python scripts/receive.py --max 50            # até 50 msgs por fila (default 20)

Peek não remove nem trava as mensagens. No modo DLQ, também mostra
`DeadLetterReason` e `DeadLetterErrorDescription` de cada mensagem.
"""

import argparse
import json
import os
import sys

from azure.servicebus import ServiceBusClient, ServiceBusSubQueue
from azure.servicebus.management import ServiceBusAdministrationClient
from dotenv import load_dotenv


def _app_props(msg) -> dict:
    def _s(v):
        return v.decode("utf-8") if isinstance(v, bytes) else v
    return {_s(k): _s(v) for k, v in (msg.application_properties or {}).items()}


def _peek(client: ServiceBusClient, queue_name: str, max_count: int, dlq: bool) -> None:
    label = f"{queue_name}/$DeadLetterQueue" if dlq else queue_name
    kwargs = {"queue_name": queue_name, "max_wait_time": 5}
    if dlq:
        kwargs["sub_queue"] = ServiceBusSubQueue.DEAD_LETTER

    try:
        with client.get_queue_receiver(**kwargs) as receiver:
            msgs = receiver.peek_messages(max_message_count=max_count)
    except Exception as e:  # noqa: BLE001
        print(f"\n=== {label} | ERRO: {e}")
        return

    print(f"\n=== {label} | visíveis: {len(msgs)}")
    for m in msgs:
        props = _app_props(m)
        print("---")
        print("  messageId:", m.message_id)
        if dlq:
            reason = props.pop("DeadLetterReason", None)
            description = props.pop("DeadLetterErrorDescription", None)
            if reason:
                print("  dlq_reason:", reason)
            if description:
                print("  dlq_desc:  ", description)
            print("  deliveries:", m.delivery_count)
        print("  props:    ", props)
        body = str(m)
        # Se for JSON, tenta pretty-print o payload (mais útil que uma linha gigante)
        try:
            parsed = json.loads(body)
            if isinstance(parsed, dict) and "payload" in parsed:
                print("  body.tipo:    ", parsed.get("tipo"))
                print("  body.payload: ", json.dumps(parsed["payload"], ensure_ascii=False)[:800])
                continue
        except (ValueError, TypeError):
            pass
        print("  body:     ", body[:800])


def _parse_args() -> tuple[bool, str | None, int]:
    p = argparse.ArgumentParser(
        description="Peek em filas (main) ou DLQs do namespace Service Bus.",
    )
    p.add_argument(
        "positional",
        nargs="*",
        default=[],
        help="'dlq' pra inspecionar DLQs; nome de fila pra filtrar. Ex.: 'dlq pedidos'.",
    )
    p.add_argument(
        "--max",
        type=int,
        default=20,
        help="Máximo de mensagens por fila (default 20).",
    )
    args = p.parse_args()

    dlq = False
    queue: str | None = None
    remaining = list(args.positional)
    if remaining and remaining[0].lower() == "dlq":
        dlq = True
        remaining.pop(0)
    if remaining:
        queue = remaining[0]
    if remaining[1:]:
        p.error(f"argumentos extras não esperados: {remaining[1:]}")
    return dlq, queue, args.max


def main() -> int:
    load_dotenv()
    conn = os.environ["AZURE_SERVICE_BUS_CONNECTION_STRING"]
    dlq, queue_filter, max_count = _parse_args()

    if queue_filter:
        queues = [queue_filter]
    else:
        with ServiceBusAdministrationClient.from_connection_string(conn) as admin:
            queues = sorted(q.name for q in admin.list_queues())
        if not queues:
            print("(nenhuma fila no namespace)")
            return 0
        mode = "DLQs" if dlq else "filas (main)"
        print(f"{mode} encontradas: {', '.join(queues)}")

    with ServiceBusClient.from_connection_string(conn) as client:
        for q in queues:
            _peek(client, q, max_count=max_count, dlq=dlq)

    return 0


if __name__ == "__main__":
    sys.exit(main())
