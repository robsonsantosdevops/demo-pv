"""Testes do handler pedido_report (SAP → Relatorio_SAP__c no SF)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import requests

from middleware.handlers.base import Action
from middleware.handlers.pedido_report import PedidoReportHandler
from middleware.integrations.sap.session import SapSessionError


@pytest.fixture
def sap_client(sap_order_fixture):
    c = MagicMock()
    c.find_order_by_numatcard.return_value = sap_order_fixture
    return c


@pytest.fixture
def sf_service():
    svc = MagicMock()
    svc.update_relatorio_sap.return_value = None
    svc.replace_relatorio_sap_linhas.return_value = 1
    svc.mark_relatorio_erro.return_value = None
    return svc


def test_pedido_report_happy_path(sap_client, sf_service, ctx_relatorio, pedido_report_payload):
    h = PedidoReportHandler(sap_client, sf_service)
    result = h.handle(pedido_report_payload, ctx_relatorio)
    assert result.action is Action.ACK

    # 1. marcou Em_Processamento
    first_call = sf_service.update_relatorio_sap.call_args_list[0]
    assert first_call.args[0] == "a01RELATORIO"
    assert first_call.kwargs == {"Status__c": "Em_Processamento"}

    # 2. buscou order no SAP
    sap_client.find_order_by_numatcard.assert_called_once_with("006TEST01")

    # 3. PATCH final com Status Recebido + campos do SAP
    final_call = sf_service.update_relatorio_sap.call_args_list[1]
    final_fields = final_call.kwargs
    assert final_call.args[0] == "a01RELATORIO"
    assert final_fields["Status__c"] == "Recebido"
    assert final_fields["DocEntry__c"] == 41367
    assert final_fields["DocNum__c"] == 7434
    assert final_fields["DocTotal__c"] == 12990.0
    assert final_fields["CardCode__c"] == "C40000"
    assert final_fields["NumAtCard__c"] == "006TEST01"
    assert final_fields["DocStatus__c"] == "Open"  # bost_Open → Open (picklist SF)
    assert final_fields["U_SF_OppName__c"] == "PED-17"
    assert final_fields["U_Curso_Nome__c"] == "Enem Online"
    assert "Data_Recebimento__c" in final_fields

    # 4. linhas substituídas
    linhas = sf_service.replace_relatorio_sap_linhas.call_args.args[1]
    assert len(linhas) == 1
    assert linhas[0]["ItemCode__c"] == "S10000"
    assert linhas[0]["Line_Number__c"] == 0
    assert linhas[0]["Total__c"] == 12990.0


def test_pedido_report_missing_opportunity_id(sap_client, sf_service, ctx_relatorio, pedido_report_payload):
    del pedido_report_payload["opportunity_id"]
    result = PedidoReportHandler(sap_client, sf_service).handle(pedido_report_payload, ctx_relatorio)
    assert result.action is Action.DLQ
    assert "opportunity_id" in result.reason
    sap_client.find_order_by_numatcard.assert_not_called()


def test_pedido_report_missing_relatorio_id(sap_client, sf_service, ctx_relatorio, pedido_report_payload):
    del pedido_report_payload["relatorio_sap_id"]
    result = PedidoReportHandler(sap_client, sf_service).handle(pedido_report_payload, ctx_relatorio)
    assert result.action is Action.DLQ
    assert "relatorio_sap_id" in result.reason


def test_pedido_report_order_not_found_marks_erro(sap_client, sf_service, ctx_relatorio, pedido_report_payload):
    sap_client.find_order_by_numatcard.return_value = None
    result = PedidoReportHandler(sap_client, sf_service).handle(pedido_report_payload, ctx_relatorio)
    assert result.action is Action.ACK

    sf_service.mark_relatorio_erro.assert_called_once()
    rel_id, mensagem = sf_service.mark_relatorio_erro.call_args.args
    assert rel_id == "a01RELATORIO"
    assert "Order não encontrada" in mensagem
    # Não tentou mexer em linhas
    sf_service.replace_relatorio_sap_linhas.assert_not_called()


def test_pedido_report_sap_session_error_retries(sap_client, sf_service, ctx_relatorio, pedido_report_payload):
    sap_client.find_order_by_numatcard.side_effect = SapSessionError("sessionId vazio")
    result = PedidoReportHandler(sap_client, sf_service).handle(pedido_report_payload, ctx_relatorio)
    assert result.action is Action.RETRY
    assert "sap_session_unavailable" in result.reason


def test_pedido_report_sap_500_retries(sap_client, sf_service, ctx_relatorio, pedido_report_payload):
    resp = MagicMock(status_code=500, text="internal")
    sap_client.find_order_by_numatcard.side_effect = requests.HTTPError(response=resp)
    result = PedidoReportHandler(sap_client, sf_service).handle(pedido_report_payload, ctx_relatorio)
    assert result.action is Action.RETRY


def test_pedido_report_sap_4xx_non_auth_marks_erro_and_acks(sap_client, sf_service, ctx_relatorio, pedido_report_payload):
    """SAP 400 'normal' (não -2014, não 401/408/429) = dado ruim → ACK + Erro."""
    resp = MagicMock(status_code=403, text="forbidden")
    sap_client.find_order_by_numatcard.side_effect = requests.HTTPError(response=resp)
    result = PedidoReportHandler(sap_client, sf_service).handle(pedido_report_payload, ctx_relatorio)
    assert result.action is Action.ACK
    sf_service.mark_relatorio_erro.assert_called_once()
    mensagem = sf_service.mark_relatorio_erro.call_args.args[1]
    assert "SAP HTTP 403" in mensagem


def test_pedido_report_sap_2014_retries(sap_client, sf_service, ctx_relatorio, pedido_report_payload):
    """Cache do Service Layer inconsistente = transiente, retry."""
    resp = MagicMock(status_code=400, text='{"error":{"code":"-2014"}}')
    sap_client.find_order_by_numatcard.side_effect = requests.HTTPError(response=resp)
    result = PedidoReportHandler(sap_client, sf_service).handle(pedido_report_payload, ctx_relatorio)
    assert result.action is Action.RETRY


def test_pedido_report_sf_500_retries(sap_client, sf_service, ctx_relatorio, pedido_report_payload):
    resp = MagicMock(status_code=500, text="sf down")
    # 1st call (Em_Processamento) passa, 2nd (update final) falha
    sf_service.update_relatorio_sap.side_effect = [None, requests.HTTPError(response=resp)]
    result = PedidoReportHandler(sap_client, sf_service).handle(pedido_report_payload, ctx_relatorio)
    assert result.action is Action.RETRY


def test_pedido_report_sf_4xx_marks_erro_and_acks(sap_client, sf_service, ctx_relatorio, pedido_report_payload):
    resp = MagicMock(status_code=400, text="FIELD_CUSTOM_VALIDATION_EXCEPTION")
    sf_service.update_relatorio_sap.side_effect = [None, requests.HTTPError(response=resp)]
    result = PedidoReportHandler(sap_client, sf_service).handle(pedido_report_payload, ctx_relatorio)
    assert result.action is Action.ACK
    # Chamou mark_relatorio_erro no final
    sf_service.mark_relatorio_erro.assert_called_once()
