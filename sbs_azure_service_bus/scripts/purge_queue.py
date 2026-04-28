"""Drena mensagens de uma fila ou DLQ, opcionalmente filtrando por tipo.

Exemplos:
    # Ver o que tem na fila (sem remover nada)
    python scripts/purge_queue.py --queue oportunidades --dry-run

    # Ver o que tem na DLQ
    python scripts/purge_queue.py --queue pedidos --dlq --dry-run

    # Drenar DLQ inteira
    python scripts/purge_queue.py --queue pedidos --dlq

    # Drenar só um tipo específico (mantém os demais)
    python scripts/purge_queue.py --queue oportunidades --filter-tipo pedido_criado

    # Drenar tudo EXCETO um tipo (útil para limpar lixo mantendo o legítimo)
    python scripts/purge_queue.py --queue oportunidades --exclude-tipo oportunidade_ganha

AVISO: `complete_message` na fila principal REMOVE a mensagem definitivamente.
       Rode --dry-run antes.
"""

import argparse
import os
import sys

from azure.servicebus import ServiceBusClient, ServiceBusSubQueue
from dotenv import load_dotenv


def _app_props(msg) -> dict[str, object]:
    def _s(v):
        return v.decode("utf-8") if isinstance(v, bytes) else v
    return {_s(k): _s(v) for k, v in (msg.application_properties or {}).items()}


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Drena mensagens de uma fila/DLQ.")
    p.add_argument("--queue", required=True, help="Fila alvo.")
    p.add_argument("--dlq", action="store_true", help="Opera sobre a sub-fila DeadLetter.")
    p.add_argument("--filter-tipo", default=None, help="Só remove mensagens com application_properties.tipo==X.")
    p.add_argument("--exclude-tipo", default=None, help="Remove tudo EXCETO mensagens com tipo==X.")
    p.add_argument("--max", type=int, default=100, help="Máximo de mensagens por execução (default 100).")
    p.add_argument("--dry-run", action="store_true", help="Só lista via peek — não remove.")
    return p.parse_args()


def main() -> int:
    load_dotenv()
    conn = os.environ["AZURE_SERVICE_BUS_CONNECTION_STRING"]
    args = _parse_args()

    if args.filter_tipo and args.exclude_tipo:
        print("ERRO: --filter-tipo e --exclude-tipo são mutuamente exclusivos", file=sys.stderr)
        return 2

    queue_label = f"{args.queue}/$DeadLetterQueue" if args.dlq else args.queue
    print(f">> fila: {queue_label}")
    if args.filter_tipo:
        print(f">> filtro: tipo == {args.filter_tipo}")
    if args.exclude_tipo:
        print(f">> filtro: tipo != {args.exclude_tipo}")
    if args.dry_run:
        print(">> DRY RUN — nada será removido")

    rx_kwargs = {"queue_name": args.queue, "max_wait_time": 10}
    if args.dlq:
        rx_kwargs["sub_queue"] = ServiceBusSubQueue.DEAD_LETTER

    with ServiceBusClient.from_connection_string(conn) as client:
        with client.get_queue_receiver(**rx_kwargs) as rx:
            if args.dry_run:
                msgs = rx.peek_messages(max_message_count=args.max)
                print(f"\npeek encontrou {len(msgs)} mensagem(ns):\n")
                for m in msgs:
                    props = _app_props(m)
                    print(
                        f"  messageId={m.message_id} "
                        f"tipo={props.get('tipo')!r} "
                        f"deliveryCount={m.delivery_count}"
                    )
                return 0

            msgs = rx.receive_messages(max_message_count=args.max, max_wait_time=10)
            print(f"\nreceive retornou {len(msgs)} mensagem(ns)\n")

            removed = kept = 0
            for m in msgs:
                props = _app_props(m)
                tipo = props.get("tipo", "")

                should_remove = True
                if args.filter_tipo is not None and tipo != args.filter_tipo:
                    should_remove = False
                if args.exclude_tipo is not None and tipo == args.exclude_tipo:
                    should_remove = False

                if should_remove:
                    rx.complete_message(m)
                    removed += 1
                    print(f"  rm   {tipo!r:25s} {m.message_id}")
                else:
                    rx.abandon_message(m)
                    kept += 1
                    print(f"  keep {tipo!r:25s} {m.message_id}")

            print(f"\nremovidas: {removed} | mantidas: {kept}")
            return 0


if __name__ == "__main__":
    sys.exit(main())
