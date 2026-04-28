"""Move mensagens da DLQ de uma fila para outra fila ativa.

Uso:
    # Ver o que há na DLQ de pedidos sem mover nada
    python scripts/redrive_dlq.py --from pedidos --to oportunidades --dry-run

    # Mover só as mensagens cujo application_properties.tipo == oportunidade_ganha
    python scripts/redrive_dlq.py --from pedidos --to oportunidades \\
        --filter-tipo oportunidade_ganha

    # Mover até 200 mensagens, sem filtro
    python scripts/redrive_dlq.py --from pedidos --to oportunidades --max 200

Preserva body, content_type, message_id, correlation_id e application_properties.
Adiciona application_properties.redriven_from = "<fila origem>/DeadLetter".
"""

import argparse
import os
import sys

from azure.servicebus import (
    ServiceBusClient,
    ServiceBusMessage,
    ServiceBusSubQueue,
)
from dotenv import load_dotenv


def _to_str(v: object) -> object:
    return v.decode("utf-8") if isinstance(v, bytes) else v


def _app_props(msg) -> dict[str, object]:
    return {
        _to_str(k): _to_str(v)
        for k, v in (msg.application_properties or {}).items()
    }


def _body_bytes(msg) -> bytes:
    body = msg.body
    if hasattr(body, "__iter__") and not isinstance(body, (bytes, bytearray)):
        return b"".join(body)
    return bytes(body or b"")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Redrive mensagens da DLQ para uma fila ativa.")
    p.add_argument("--from", dest="source", required=True, help="Fila origem (a DLQ dela será lida).")
    p.add_argument("--to", dest="dest", required=True, help="Fila destino para reenvio.")
    p.add_argument("--filter-tipo", default=None, help="Só reenvia mensagens com application_properties.tipo==X.")
    p.add_argument("--max", type=int, default=50, help="Máximo de mensagens a ler por execução (default: 50).")
    p.add_argument("--dry-run", action="store_true", help="Só lista via peek, não move nada.")
    return p.parse_args()


def main() -> int:
    load_dotenv()
    conn = os.environ["AZURE_SERVICE_BUS_CONNECTION_STRING"]
    args = _parse_args()

    print(f">> source DLQ: {args.source}/$DeadLetterQueue")
    print(f">> dest queue: {args.dest}")
    if args.filter_tipo:
        print(f">> filter tipo: {args.filter_tipo}")
    if args.dry_run:
        print(">> DRY RUN — nenhuma mensagem será movida")

    with ServiceBusClient.from_connection_string(conn) as client:
        dlq_rx = client.get_queue_receiver(
            queue_name=args.source,
            sub_queue=ServiceBusSubQueue.DEAD_LETTER,
            max_wait_time=10,
        )
        sender = client.get_queue_sender(args.dest)

        with dlq_rx, sender:
            if args.dry_run:
                msgs = dlq_rx.peek_messages(max_message_count=args.max)
                print(f"\nDLQ tem ao menos {len(msgs)} mensagem(ns) (peek):\n")
                for m in msgs:
                    props = _app_props(m)
                    print(
                        f"  messageId={m.message_id} "
                        f"tipo={props.get('tipo')!r} "
                        f"dlq_reason={props.get('DeadLetterReason')!r} "
                        f"delivery_count={m.delivery_count}"
                    )
                return 0

            msgs = dlq_rx.receive_messages(
                max_message_count=args.max, max_wait_time=10
            )
            print(f"\nDLQ retornou {len(msgs)} mensagem(ns) bloqueadas para reprocessar\n")

            moved = skipped = 0
            for m in msgs:
                props = _app_props(m)
                tipo = props.get("tipo")

                if args.filter_tipo and tipo != args.filter_tipo:
                    dlq_rx.abandon_message(m)
                    skipped += 1
                    print(f"  skip (tipo!={args.filter_tipo}): {m.message_id}")
                    continue

                props["redriven_from"] = f"{args.source}/DeadLetter"

                new_msg = ServiceBusMessage(
                    body=_body_bytes(m),
                    content_type=m.content_type,
                    message_id=m.message_id,
                    application_properties=props,
                )
                if m.correlation_id:
                    new_msg.correlation_id = m.correlation_id

                try:
                    sender.send_messages(new_msg)
                except Exception as e:  # noqa: BLE001
                    dlq_rx.abandon_message(m)
                    print(f"  ERRO enviando {m.message_id}: {e} — mantido na DLQ")
                    continue

                dlq_rx.complete_message(m)
                moved += 1
                print(f"  ok  -> {args.dest}: messageId={m.message_id} tipo={tipo!r}")

            print(f"\nmovidas: {moved} | puladas: {skipped}")
            return 0


if __name__ == "__main__":
    sys.exit(main())
