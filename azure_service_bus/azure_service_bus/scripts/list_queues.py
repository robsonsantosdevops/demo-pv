# list_queues.py
import os
from dotenv import load_dotenv
from azure.servicebus.management import ServiceBusAdministrationClient

load_dotenv()
CONN_STR = os.getenv("AZURE_SERVICE_BUS_CONNECTION_STRING")

with ServiceBusAdministrationClient.from_connection_string(CONN_STR) as admin:
    for q in admin.list_queues():
        runtime = admin.get_queue_runtime_properties(q.name)
        print(f"- {q.name} | active={runtime.active_message_count} | dlq={runtime.dead_letter_message_count}")