"""Testes de middleware.dispatcher.Dispatcher."""

from __future__ import annotations

from unittest.mock import MagicMock

from middleware.dispatcher import KNOWN_TYPES, Dispatcher


def test_resolve_returns_registered_handler():
    handler = MagicMock()
    d = Dispatcher({("pedidos", "pedido_criado"): handler})
    assert d.resolve("pedidos", "pedido_criado") is handler


def test_resolve_returns_none_when_unregistered():
    d = Dispatcher({})
    assert d.resolve("pedidos", "desconhecido") is None
    assert d.resolve("outra-fila", "tipo-qualquer") is None


def test_resolve_respects_queue_boundary():
    """Handler registrado em (pedidos, X) não deve resolver em (oportunidades, X)."""
    handler = MagicMock()
    d = Dispatcher({("pedidos", "pedido_criado"): handler})
    assert d.resolve("oportunidades", "pedido_criado") is None


def test_known_types_covers_expected_routes():
    # pedido_report / relatorio_sap_request: sinônimos aceitos em ambas filas
    # (pedidos como trânsito via Forwarder; relatorios como canônico).
    assert KNOWN_TYPES["pedidos"] == {
        "pedido_criado", "pagamento_aprovado", "pedido_report", "relatorio_sap_request",
    }
    assert KNOWN_TYPES["oportunidades"] == {"oportunidade_ganha"}
    assert KNOWN_TYPES["contatos"] == {"aluno_cadastrado"}
    assert KNOWN_TYPES["relatorios"] == {"pedido_report", "relatorio_sap_request"}
