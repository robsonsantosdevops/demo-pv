"""Loop de consumo peek-lock com graceful shutdown."""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import TYPE_CHECKING

from azure.servicebus import ServiceBusClient, ServiceBusReceiveMode
from azure.servicebus.exceptions import ServiceBusError

from middleware.config import Config
from middleware.dispatcher import Dispatcher
from middleware.handlers.base import Action, HandlerContext
from middleware.health import HealthState

if TYPE_CHECKING:
    from azure.servicebus import ServiceBusReceivedMessage

log = logging.getLogger("middleware.consumer")


class Consumer:
    def __init__(
        self,
        config: Config,
        dispatcher: Dispatcher,
        health: HealthState,
        shutdown: threading.Event,
    ) -> None:
        self.config = config
        self.dispatcher = dispatcher
        self.health = health
        self.shutdown = shutdown

    def run(self) -> None:
        log.info(
            "consumer iniciando",
            extra={"queue": self.config.queue_name, "status": "starting"},
        )
        with ServiceBusClient.from_connection_string(
            self.config.service_bus_connection_string
        ) as client:
            with client.get_queue_receiver(
                queue_name=self.config.queue_name,
                receive_mode=ServiceBusReceiveMode.PEEK_LOCK,
                max_wait_time=self.config.max_wait_time,
            ) as receiver:
                self.health.mark_ready()
                log.info(
                    "consumer pronto",
                    extra={"queue": self.config.queue_name, "status": "ready"},
                )
                self._loop(receiver)

        self.health.mark_not_ready()
        log.info(
            "consumer encerrado",
            extra={"queue": self.config.queue_name, "status": "stopped"},
        )

    def _loop(self, receiver) -> None:  # type: ignore[no-untyped-def]
        while not self.shutdown.is_set():
            try:
                batch = receiver.receive_messages(
                    max_message_count=self.config.max_message_count,
                    max_wait_time=self.config.max_wait_time,
                )
            except ServiceBusError as e:
                log.exception(
                    "erro lendo do service bus",
                    extra={"queue": self.config.queue_name, "status": "error", "reason": str(e)},
                )
                time.sleep(2)
                continue

            if not batch:
                continue

            for msg in batch:
                if self.shutdown.is_set():
                    # Não processa novas mensagens; abandona para que outro pod pegue.
                    try:
                        receiver.abandon_message(msg)
                    except ServiceBusError:
                        log.exception("falha abandonando mensagem durante shutdown")
                    continue
                self._process(receiver, msg)

    def _process(self, receiver, msg: "ServiceBusReceivedMessage") -> None:  # type: ignore[no-untyped-def]
        app_props = {
            (k.decode() if isinstance(k, bytes) else k): (v.decode() if isinstance(v, bytes) else v)
            for k, v in (msg.application_properties or {}).items()
        }
        tipo = app_props.get("tipo", "")
        traceparent = app_props.get("traceparent")
        raw_body = b"".join(msg.body) if hasattr(msg.body, "__iter__") else bytes(msg.body or b"")

        base_extra = {
            "queue": self.config.queue_name,
            "message_id": msg.message_id,
            "tipo": tipo,
            "delivery_count": msg.delivery_count,
        }

        try:
            body = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            log.error(
                "body não é JSON",
                extra={**base_extra, "status": "dlq", "reason": f"invalid_json:{e}"},
            )
            receiver.dead_letter_message(
                msg, reason="invalid_json", error_description=str(e)[:512]
            )
            return

        payload = body.get("payload") if isinstance(body, dict) else None
        if not isinstance(payload, dict):
            log.error(
                "payload ausente ou não é objeto",
                extra={**base_extra, "status": "dlq", "reason": "missing_payload"},
            )
            receiver.dead_letter_message(
                msg, reason="missing_payload", error_description="body.payload não é dict"
            )
            return

        handler = self.dispatcher.resolve(self.config.queue_name, tipo)
        if handler is None:
            log.error(
                "tipo desconhecido pra esta fila",
                extra={**base_extra, "status": "dlq", "reason": "unknown_type"},
            )
            receiver.dead_letter_message(
                msg, reason="unknown_type", error_description=f"tipo={tipo} queue={self.config.queue_name}"
            )
            return

        ctx = HandlerContext(
            queue=self.config.queue_name,
            tipo=tipo,
            message_id=msg.message_id,
            correlation_id=payload.get("correlation_id"),
            delivery_count=msg.delivery_count,
            traceparent=traceparent,
        )

        start = time.monotonic()
        try:
            result = handler.handle(payload, ctx)
        except Exception as e:  # noqa: BLE001
            duration_ms = int((time.monotonic() - start) * 1000)
            log.exception(
                "handler lançou exceção — abandonando pra retry",
                extra={
                    **base_extra,
                    "handler": getattr(handler, "name", type(handler).__name__),
                    "correlation_id": payload.get("correlation_id"),
                    "duration_ms": duration_ms,
                    "status": "retry",
                    "reason": f"exception:{type(e).__name__}",
                },
            )
            receiver.abandon_message(msg)
            return

        duration_ms = int((time.monotonic() - start) * 1000)
        extra = {
            **base_extra,
            "handler": getattr(handler, "name", type(handler).__name__),
            "correlation_id": payload.get("correlation_id"),
            "duration_ms": duration_ms,
            "status": result.action.value,
            "reason": result.reason,
        }

        if result.action is Action.ACK:
            receiver.complete_message(msg)
            log.info("mensagem processada", extra=extra)
        elif result.action is Action.RETRY:
            receiver.abandon_message(msg)
            log.warning("mensagem abandonada pra retry", extra=extra)
        else:  # DLQ
            receiver.dead_letter_message(
                msg,
                reason=result.reason or "handler_dlq",
                error_description=result.reason or "",
            )
            log.error("mensagem enviada pra DLQ", extra=extra)
