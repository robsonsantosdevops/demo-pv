"""Forwarder genérico: republica a mensagem numa outra fila do mesmo namespace.

Uso: quando um tipo chega numa fila "errada" (ex.: Apex ainda publica em
`pedidos` mas o tipo real pertence à fila `relatorios`). O forwarder
preserva body/application_properties e re-emite um messageId com sufixo
`-forwarded` pra rastreabilidade.

Cria um ServiceBusClient novo por mensagem — simples; custo aceitável pra
os 1-2 eventos/dia do caso atual. Se virar hot path, vale cachear um
sender por fila.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from azure.servicebus import ServiceBusClient, ServiceBusMessage

from middleware.handlers.base import HandleResult, Handler, HandlerContext

log = logging.getLogger("middleware.handler.forwarder")


class ForwarderHandler(Handler):
    name = "forwarder"

    def __init__(self, sb_connection_string: str, target_queue: str) -> None:
        self.sb_connection_string = sb_connection_string
        self.target_queue = target_queue

    def handle(self, payload: dict, ctx: HandlerContext) -> HandleResult:
        body = {
            "tipo": ctx.tipo,
            "payload": payload,
            "timestamp": datetime.now(timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
        }
        app_props: dict = {"tipo": ctx.tipo, "forwarded_from": ctx.queue}
        if ctx.traceparent:
            app_props["traceparent"] = ctx.traceparent

        message = ServiceBusMessage(
            body=json.dumps(body, ensure_ascii=False),
            content_type="application/json",
            message_id=f"{ctx.message_id or ctx.tipo}-forwarded",
            application_properties=app_props,
        )

        with ServiceBusClient.from_connection_string(self.sb_connection_string) as client:
            with client.get_queue_sender(self.target_queue) as sender:
                sender.send_messages(message)

        log.info(
            "mensagem encaminhada",
            extra={
                "handler": self.name,
                "status": "ok",
                "correlation_id": ctx.correlation_id,
                "reason": f"{ctx.queue}→{self.target_queue} tipo={ctx.tipo}",
            },
        )
        return HandleResult.ok()
