"""Contrato dos handlers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class Action(str, Enum):
    ACK = "ack"       # complete_message
    RETRY = "retry"   # abandon_message (volta pra fila, incrementa delivery count)
    DLQ = "dlq"       # dead_letter_message (erro permanente)


@dataclass(frozen=True)
class HandleResult:
    action: Action
    reason: str | None = None

    @classmethod
    def ok(cls) -> "HandleResult":
        return cls(Action.ACK)

    @classmethod
    def retry(cls, reason: str) -> "HandleResult":
        return cls(Action.RETRY, reason)

    @classmethod
    def dlq(cls, reason: str) -> "HandleResult":
        return cls(Action.DLQ, reason)


@dataclass(frozen=True)
class HandlerContext:
    queue: str
    tipo: str
    message_id: str | None
    correlation_id: str | None
    delivery_count: int
    traceparent: str | None


class Handler(Protocol):
    name: str

    def handle(self, payload: dict, ctx: HandlerContext) -> HandleResult: ...
