"""Testes do handler pagamento_aprovado."""

from __future__ import annotations

from middleware.handlers.base import Action
from middleware.handlers.pagamento_aprovado import PagamentoAprovadoHandler


def test_pagamento_closes_opportunity(sf_service, ctx_pagamento, pagamento_payload):
    sf_service.find_opportunity_by_correlation.return_value = {
        "Id": "006OPP",
        "StageName": "Prospecting",
        "Description": "old",
    }
    result = PagamentoAprovadoHandler(sf_service).handle(pagamento_payload, ctx_pagamento)
    assert result.action is Action.ACK

    sf_service.update_opportunity.assert_called_once()
    opp_id, fields = sf_service.update_opportunity.call_args.args[0], sf_service.update_opportunity.call_args.kwargs
    assert opp_id == "006OPP"
    assert fields["StageName"] == "Closed Won"
    assert fields["Amount"] == 199.9
    assert fields["Pagamento_Id__c"] == 99
    assert fields["Forma_Pagamento__c"] == "pix"
    assert fields["Status_Pagamento__c"] == "aprovado"
    assert fields["Status_Pedido__c"] == "pago"
    # cartao_final é None no payload pix → não deve entrar
    assert "Cartao_Final__c" not in fields


def test_pagamento_falls_back_to_search_by_name(sf_service, ctx_pagamento, pagamento_payload):
    sf_service.find_opportunity_by_correlation.return_value = None
    sf_service.find_opportunity_by_name.return_value = {
        "Id": "006OPPLEGACY",
        "StageName": "Prospecting",
        "Description": "",
    }
    result = PagamentoAprovadoHandler(sf_service).handle(pagamento_payload, ctx_pagamento)
    assert result.action is Action.ACK
    sf_service.find_opportunity_by_correlation.assert_called_once_with("corr-001")
    sf_service.find_opportunity_by_name.assert_called_once_with("PED-TEST-001")
    sf_service.update_opportunity.assert_called_once()


def test_pagamento_fallback_by_derived_numero_pedido(sf_service, ctx_pagamento, pagamento_payload):
    """Sem numero_pedido mas com pedido_id → fallback usa PED-<id>."""
    del pagamento_payload["numero_pedido"]
    sf_service.find_opportunity_by_correlation.return_value = None
    sf_service.find_opportunity_by_name.return_value = {
        "Id": "006LEG", "StageName": "Prospecting", "Description": "",
    }
    result = PagamentoAprovadoHandler(sf_service).handle(pagamento_payload, ctx_pagamento)
    assert result.action is Action.ACK
    sf_service.find_opportunity_by_name.assert_called_once_with("PED-42")


def test_pagamento_no_fallback_when_only_correlation(sf_service, ctx_pagamento, pagamento_payload):
    """Sem numero_pedido nem pedido_id, handler pula o fallback por name."""
    del pagamento_payload["numero_pedido"]
    del pagamento_payload["pedido_id"]
    sf_service.find_opportunity_by_correlation.return_value = None
    result = PagamentoAprovadoHandler(sf_service).handle(pagamento_payload, ctx_pagamento)
    assert result.action is Action.RETRY
    sf_service.find_opportunity_by_name.assert_not_called()


def test_pagamento_retries_if_opp_not_found(sf_service, ctx_pagamento, pagamento_payload):
    sf_service.find_opportunity_by_correlation.return_value = None
    sf_service.find_opportunity_by_name.return_value = None
    result = PagamentoAprovadoHandler(sf_service).handle(pagamento_payload, ctx_pagamento)
    assert result.action is Action.RETRY
    assert "opp_not_found" in result.reason
    sf_service.update_opportunity.assert_not_called()


def test_pagamento_idempotent_on_closed_won(sf_service, ctx_pagamento, pagamento_payload):
    sf_service.find_opportunity_by_correlation.return_value = {
        "Id": "006OPP",
        "StageName": "Closed Won",
        "Description": "done",
    }
    result = PagamentoAprovadoHandler(sf_service).handle(pagamento_payload, ctx_pagamento)
    assert result.action is Action.ACK
    sf_service.update_opportunity.assert_not_called()


def test_pagamento_keeps_cartao_final_when_present(sf_service, ctx_pagamento, pagamento_payload):
    pagamento_payload["forma_pagamento"] = "cartao_credito"
    pagamento_payload["cartao_final"] = "1234"
    sf_service.find_opportunity_by_correlation.return_value = {
        "Id": "006OPP", "StageName": "Prospecting", "Description": "",
    }
    PagamentoAprovadoHandler(sf_service).handle(pagamento_payload, ctx_pagamento)
    fields = sf_service.update_opportunity.call_args.kwargs
    assert fields["Cartao_Final__c"] == "1234"


def test_pagamento_missing_valor_goes_to_dlq(sf_service, ctx_pagamento, pagamento_payload):
    del pagamento_payload["valor"]
    result = PagamentoAprovadoHandler(sf_service).handle(pagamento_payload, ctx_pagamento)
    assert result.action is Action.DLQ
    assert "valor" in result.reason
    sf_service.find_opportunity_by_correlation.assert_not_called()


def test_pagamento_missing_correlation_goes_to_dlq(sf_service, ctx_pagamento, pagamento_payload):
    del pagamento_payload["correlation_id"]
    result = PagamentoAprovadoHandler(sf_service).handle(pagamento_payload, ctx_pagamento)
    assert result.action is Action.DLQ
    assert "correlation_id" in result.reason


def test_pagamento_invalid_valor_goes_to_dlq(sf_service, ctx_pagamento, pagamento_payload):
    pagamento_payload["valor"] = "abc"
    result = PagamentoAprovadoHandler(sf_service).handle(pagamento_payload, ctx_pagamento)
    assert result.action is Action.DLQ
    assert "invalid_valor" in result.reason
