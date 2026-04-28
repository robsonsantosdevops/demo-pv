"""Testes do handler oportunidade_ganha (→ SAP B1)."""

from __future__ import annotations

from unittest.mock import MagicMock

import requests

from middleware.handlers.base import Action
from middleware.handlers.oportunidade_ganha import OportunidadeGanhaHandler
from middleware.integrations.sap.session import SapSessionError


def test_opp_creates_order_happy_path(sap_client, ctx_opp, opp_payload):
    result = OportunidadeGanhaHandler(sap_client).handle(opp_payload, ctx_opp)
    assert result.action is Action.ACK

    sap_client.create_order.assert_called_once()
    payload = sap_client.create_order.call_args.args[0]
    assert payload["CardCode"] == "C40000"
    assert payload["BPL_IDAssignedToInvoice"] == 1
    assert payload["NumAtCard"] == "006OPP12345"  # chave idempotente
    assert payload["U_SF_OppId"] == "006OPP12345"
    assert payload["U_SF_OppName"] == "SB Test Opp"
    assert payload["DocumentLines"][0]["ItemCode"] == "S10000"
    assert payload["DocumentLines"][0]["Quantity"] == 1.0
    assert payload["DocumentLines"][0]["UnitPrice"] == 1500.0
    assert "Comments" in payload


def test_opp_enriches_from_salesforce(sap_client, ctx_opp, opp_payload):
    """Com sf_service, handler puxa Curso/Aluno e popula UDFs."""
    sf = MagicMock()
    sf.get_opportunity_by_id.return_value = {
        "Name": "PED-ENRICH-1",
        "Correlation_Id__c": "corr-enrich",
        "Pedido_Id__c": 42.0,
        "Aluno_Nome__c": "Jon Snow",
        "Aluno_Email__c": "jon@wall.test",
        "Curso_Nome__c": "Medicina Online",
        "Curso_Descricao__c": "Curso longo de Medicina",
    }
    OportunidadeGanhaHandler(sap_client, sf_service=sf).handle(opp_payload, ctx_opp)

    sf.get_opportunity_by_id.assert_called_once()
    payload = sap_client.create_order.call_args.args[0]
    assert payload["U_Curso_Nome"] == "Medicina Online"
    assert payload["U_Curso_Descricao"] == "Curso longo de Medicina"
    assert payload["U_Aluno_Nome"] == "Jon Snow"
    assert payload["U_Aluno_Email"] == "jon@wall.test"
    assert payload["U_Pedido_Id"] == 42  # convertido de 42.0 para int
    # Opp Name do SF sobrescreve o payload.name (mais autoritativo)
    assert payload["U_SF_OppName"] == "PED-ENRICH-1"
    # Comments enriquecido com curso/aluno
    assert "Medicina Online" in payload["Comments"]
    assert "Jon Snow" in payload["Comments"]


def test_opp_sf_enrichment_failure_is_fail_soft(sap_client, ctx_opp, opp_payload):
    """Se SF falhar, handler segue com dados do payload e cria Order normalmente."""
    sf = MagicMock()
    sf.get_opportunity_by_id.side_effect = requests.ConnectionError("sf down")

    result = OportunidadeGanhaHandler(sap_client, sf_service=sf).handle(opp_payload, ctx_opp)
    assert result.action is Action.ACK
    sap_client.create_order.assert_called_once()
    payload = sap_client.create_order.call_args.args[0]
    # UDFs de enrichment ausentes (None removido pelo filtro); básicos presentes
    assert payload["U_SF_OppId"] == "006OPP12345"
    assert "U_Curso_Nome" not in payload
    assert "U_Aluno_Nome" not in payload


def test_opp_without_sf_service_still_creates_basic_order(sap_client, ctx_opp, opp_payload):
    """sf_service=None → sem enriquecimento, Order criada só com dados do payload."""
    result = OportunidadeGanhaHandler(sap_client, sf_service=None).handle(opp_payload, ctx_opp)
    assert result.action is Action.ACK
    payload = sap_client.create_order.call_args.args[0]
    assert payload["U_SF_OppId"] == "006OPP12345"
    assert "U_Curso_Nome" not in payload
    assert payload["Comments"].startswith("Opp: SB Test Opp (006OPP12345)")


def test_opp_idempotent_when_order_already_exists(sap_client, ctx_opp, opp_payload):
    """Se filter NumAtCard retorna uma Order, não deve criar nova."""
    sap_client.get.return_value = {
        "value": [{"DocEntry": 41343, "DocNum": 7419, "NumAtCard": "006OPP12345"}]
    }
    result = OportunidadeGanhaHandler(sap_client).handle(opp_payload, ctx_opp)
    assert result.action is Action.ACK
    sap_client.create_order.assert_not_called()


def test_opp_missing_required_goes_to_dlq(sap_client, ctx_opp, opp_payload):
    del opp_payload["amount"]
    result = OportunidadeGanhaHandler(sap_client).handle(opp_payload, ctx_opp)
    assert result.action is Action.DLQ
    sap_client.create_order.assert_not_called()


def test_opp_invalid_amount_goes_to_dlq(sap_client, ctx_opp, opp_payload):
    opp_payload["amount"] = "not-a-number"
    result = OportunidadeGanhaHandler(sap_client).handle(opp_payload, ctx_opp)
    assert result.action is Action.DLQ
    assert "invalid_amount" in result.reason


def test_opp_session_error_triggers_retry(sap_client, ctx_opp, opp_payload):
    sap_client.create_order.side_effect = SapSessionError("sessionId vazio")
    result = OportunidadeGanhaHandler(sap_client).handle(opp_payload, ctx_opp)
    assert result.action is Action.RETRY
    assert "sap_session_unavailable" in result.reason


def test_opp_http_400_goes_to_dlq(sap_client, ctx_opp, opp_payload):
    resp = MagicMock(status_code=400, text="Bad Request")
    sap_client.create_order.side_effect = requests.HTTPError(response=resp)
    result = OportunidadeGanhaHandler(sap_client).handle(opp_payload, ctx_opp)
    assert result.action is Action.DLQ
    assert "sap_http_400" in result.reason


def test_opp_http_400_code_minus_2014_is_retry(sap_client, ctx_opp, opp_payload):
    """SAP code -2014 (schema stale após criar UDFs) é transiente → RETRY."""
    body = '{"error":{"code":"-2014","message":"Internal error (-2014) occurred"}}'
    resp = MagicMock(status_code=400, text=body)
    sap_client.create_order.side_effect = requests.HTTPError(response=resp)
    result = OportunidadeGanhaHandler(sap_client).handle(opp_payload, ctx_opp)
    assert result.action is Action.RETRY
    assert "sap_schema_stale" in result.reason


def test_opp_http_500_triggers_retry(sap_client, ctx_opp, opp_payload):
    resp = MagicMock(status_code=500, text="Internal Server Error")
    sap_client.create_order.side_effect = requests.HTTPError(response=resp)
    result = OportunidadeGanhaHandler(sap_client).handle(opp_payload, ctx_opp)
    assert result.action is Action.RETRY
    assert "sap_http_500" in result.reason


def test_opp_http_401_triggers_retry(sap_client, ctx_opp, opp_payload):
    """401 é tratado como transiente — o client já faz retry interno mas se persistir, retry."""
    resp = MagicMock(status_code=401, text="Unauthorized")
    sap_client.create_order.side_effect = requests.HTTPError(response=resp)
    result = OportunidadeGanhaHandler(sap_client).handle(opp_payload, ctx_opp)
    assert result.action is Action.RETRY


def test_opp_network_error_triggers_retry(sap_client, ctx_opp, opp_payload):
    sap_client.create_order.side_effect = requests.ConnectionError("connection refused")
    result = OportunidadeGanhaHandler(sap_client).handle(opp_payload, ctx_opp)
    assert result.action is Action.RETRY
    assert "sap_network" in result.reason


def test_opp_comments_include_opportunity_id_for_audit(sap_client, ctx_opp, opp_payload):
    OportunidadeGanhaHandler(sap_client).handle(opp_payload, ctx_opp)
    payload = sap_client.create_order.call_args.args[0]
    assert "006OPP12345" in payload["Comments"]


def test_opp_idempotency_check_failure_is_non_blocking(sap_client, ctx_opp, opp_payload):
    """Se o GET do filter falhar, handler segue criando (fail-open, melhor duplicata que travar)."""
    resp = MagicMock(status_code=500, text="err")
    sap_client.get.side_effect = requests.HTTPError(response=resp)
    result = OportunidadeGanhaHandler(sap_client).handle(opp_payload, ctx_opp)
    assert result.action is Action.ACK
    sap_client.create_order.assert_called_once()
