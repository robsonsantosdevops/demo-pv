"""Garante a existência das filas usadas pelo middleware.

Idempotente: se a fila já existir, só mostra as propriedades e segue.
"""

import os
from datetime import timedelta

from azure.servicebus.management import ServiceBusAdministrationClient
from azure.core.exceptions import ResourceExistsError
from dotenv import load_dotenv

load_dotenv()
CONN_STR = os.environ["AZURE_SERVICE_BUS_CONNECTION_STRING"]

QUEUE_NAMES = ["pedidos", "oportunidades", "contatos", "relatorios"]
DEFAULT_SPEC = {
    "lock_duration": timedelta(minutes=5),
    "max_delivery_count": 5,
    "default_message_time_to_live": timedelta(days=14),
    "dead_lettering_on_message_expiration": True,
    "enable_batched_operations": True,
}


def main() -> None:
    with ServiceBusAdministrationClient.from_connection_string(CONN_STR) as admin:
        for name in QUEUE_NAMES:
            try:
                admin.create_queue(name, **DEFAULT_SPEC)
                print(f"[ok]   criada: {name}")
            except ResourceExistsError:
                print(f"[skip] ja existe: {name}")

            q = admin.get_queue(name)
            print(
                f"   lock={q.lock_duration} "
                f"maxDelivery={q.max_delivery_count} "
                f"ttl={q.default_message_time_to_live} "
                f"dlqOnExpire={q.dead_lettering_on_message_expiration}"
            )


if __name__ == "__main__":
    main()
