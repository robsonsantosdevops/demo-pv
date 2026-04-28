"""Testes de middleware.handlers.base (HandleResult, Action)."""

from __future__ import annotations

from middleware.handlers.base import Action, HandleResult, HandlerContext


def test_handle_result_ok_factory():
    r = HandleResult.ok()
    assert r.action is Action.ACK
    assert r.reason is None


def test_handle_result_retry_factory():
    r = HandleResult.retry("network glitch")
    assert r.action is Action.RETRY
    assert r.reason == "network glitch"


def test_handle_result_dlq_factory():
    r = HandleResult.dlq("invalid_payload")
    assert r.action is Action.DLQ
    assert r.reason == "invalid_payload"


def test_action_values_match_log_convention():
    # Os values são usados no JSON log do consumer como "status": result.action.value
    assert Action.ACK.value == "ack"
    assert Action.RETRY.value == "retry"
    assert Action.DLQ.value == "dlq"


def test_handler_context_is_frozen():
    ctx = HandlerContext(
        queue="pedidos",
        tipo="pedido_criado",
        message_id="m1",
        correlation_id="c1",
        delivery_count=0,
        traceparent=None,
    )
    # dataclass(frozen=True) — deve levantar ao tentar mutar
    import dataclasses
    try:
        ctx.queue = "oportunidades"  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        return
    assert False, "HandlerContext deveria ser frozen"
