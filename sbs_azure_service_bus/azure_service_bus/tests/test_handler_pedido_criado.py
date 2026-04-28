"""Testes do handler pedido_criado."""

from __future__ import annotations

import json

from middleware.handlers.base import Action
from middleware.handlers.pedido_criado import PedidoCriadoHandler


def test_pedido_criado_happy_path(sf_service, ctx, pedido_payload):
    handler = PedidoCriadoHandler(sf_service)
    result = handler.handle(pedido_payload, ctx)

    assert result.action is Action.ACK

    sf_service.ensure_account_master.assert_called_once()
    # Sem Contact pré-existente (find_contact_by_aluno_id=None), cai no fallback
    sf_service.upsert_contact_by_email.assert_called_once_with(
        "001ACCOUNTMASTER", "Fulano Teste", "fulano@teste.com"
    )
    sf_service.upsert_opportunity_by_correlation.assert_called_once()
    # E cria OpportunityContactRole no fim
    sf_service.ensure_opportunity_contact_role.assert_called_once_with(
        "006OPPMOCK", "003CONTACTMOCK", role="Aluno"
    )


def test_pedido_uses_existing_contact_from_aluno_id(sf_service, ctx, pedido_payload):
    """Se Contact com Aluno_Id__c já existe, pula o fallback por email."""
    sf_service.find_contact_by_aluno_id.return_value = {"Id": "003FROMID", "Email": "x@y.z"}
    PedidoCriadoHandler(sf_service).handle(pedido_payload, ctx)
    sf_service.upsert_contact_by_email.assert_not_called()
    sf_service.ensure_opportunity_contact_role.assert_called_once_with(
        "006OPPMOCK", "003FROMID", role="Aluno"
    )


def test_pedido_criado_fields_populated(sf_service, ctx, pedido_payload):
    PedidoCriadoHandler(sf_service).handle(pedido_payload, ctx)

    call_args = sf_service.upsert_opportunity_by_correlation.call_args
    correlation_id, fields = call_args.args
    assert correlation_id == "corr-001"
    # Campos custom
    assert fields["Correlation_Id__c"] == "corr-001"
    assert fields["Pedido_Id__c"] == 42
    assert fields["Aluno_Id__c"] == 7
    assert fields["Aluno_Nome__c"] == "Fulano Teste"
    assert fields["Aluno_Email__c"] == "fulano@teste.com"
    assert fields["Parcelas__c"] == 3
    assert fields["Status_Checkout__c"] == "aguardando_pagamento"
    assert fields["Pedido_Created_At__c"] == "2026-04-23T00:00:00.000Z"
    # Itens serializados como JSON
    parsed = json.loads(fields["Itens_Json__c"])
    assert parsed[0]["curso_id"] == "c1"
    # Campos standard
    assert fields["Name"] == "PED-TEST-001"
    assert fields["StageName"] == "Prospecting"
    assert fields["Amount"] == 199.9
    assert fields["AccountId"] == "001ACCOUNTMASTER"
    assert "Description" in fields


def test_pedido_criado_drops_none_fields(sf_service, ctx, pedido_payload):
    """Chaves com valor None não devem ir pro payload (evita null no SF)."""
    pedido_payload["parcelas"] = None  # simula campo ausente
    PedidoCriadoHandler(sf_service).handle(pedido_payload, ctx)
    fields = sf_service.upsert_opportunity_by_correlation.call_args.args[1]
    assert "Parcelas__c" not in fields


def test_pedido_criado_missing_fields_goes_to_dlq(sf_service, ctx, pedido_payload):
    del pedido_payload["aluno_email"]
    result = PedidoCriadoHandler(sf_service).handle(pedido_payload, ctx)
    assert result.action is Action.DLQ
    assert "aluno_email" in result.reason
    sf_service.upsert_opportunity_by_correlation.assert_not_called()


def test_pedido_criado_derives_numero_pedido_from_pedido_id(sf_service, ctx, pedido_payload):
    """Checkout novo não manda numero_pedido — handler deriva de pedido_id."""
    del pedido_payload["numero_pedido"]
    result = PedidoCriadoHandler(sf_service).handle(pedido_payload, ctx)
    assert result.action is Action.ACK
    fields = sf_service.upsert_opportunity_by_correlation.call_args.args[1]
    assert fields["Name"] == "PED-42"  # derivado do pedido_id=42 do fixture


def test_pedido_criado_dlq_when_neither_numero_nor_pedido_id(sf_service, ctx, pedido_payload):
    del pedido_payload["numero_pedido"]
    del pedido_payload["pedido_id"]
    result = PedidoCriadoHandler(sf_service).handle(pedido_payload, ctx)
    assert result.action is Action.DLQ
    assert "numero_pedido|pedido_id" in result.reason


def test_pedido_criado_populates_curso_fields_from_first_item(sf_service, ctx, pedido_payload):
    """Checkout agora manda curso_descricao (e curso_titulo já vinha)."""
    pedido_payload["itens"][0]["curso_descricao"] = "Descrição detalhada do curso"
    PedidoCriadoHandler(sf_service).handle(pedido_payload, ctx)
    fields = sf_service.upsert_opportunity_by_correlation.call_args.args[1]
    assert fields["Curso_Nome__c"] == "Curso Um"  # curso_titulo do fixture
    assert fields["Curso_Descricao__c"] == "Descrição detalhada do curso"


def test_pedido_criado_omits_curso_fields_when_absent(sf_service, ctx, pedido_payload):
    """Sem curso_descricao no item → campo Curso_Descricao__c não vai no payload."""
    pedido_payload["itens"] = [{"curso_id": "x", "quantidade": 1}]  # sem curso_titulo/curso_descricao
    PedidoCriadoHandler(sf_service).handle(pedido_payload, ctx)
    fields = sf_service.upsert_opportunity_by_correlation.call_args.args[1]
    assert "Curso_Nome__c" not in fields
    assert "Curso_Descricao__c" not in fields


def test_pedido_criado_handles_empty_itens_gracefully(sf_service, ctx, pedido_payload):
    pedido_payload["itens"] = []
    result = PedidoCriadoHandler(sf_service).handle(pedido_payload, ctx)
    assert result.action is Action.ACK
    fields = sf_service.upsert_opportunity_by_correlation.call_args.args[1]
    assert "Curso_Nome__c" not in fields
    assert "Curso_Descricao__c" not in fields


def test_pedido_criado_invalid_total_goes_to_dlq(sf_service, ctx, pedido_payload):
    pedido_payload["total"] = "nao-numero"
    result = PedidoCriadoHandler(sf_service).handle(pedido_payload, ctx)
    assert result.action is Action.DLQ
    assert "invalid_total" in result.reason


def test_pedido_criado_without_correlation_id_goes_to_dlq(sf_service, ctx, pedido_payload):
    del pedido_payload["correlation_id"]
    result = PedidoCriadoHandler(sf_service).handle(pedido_payload, ctx)
    assert result.action is Action.DLQ


def test_pedido_criado_empty_itens_serializes_empty_array(sf_service, ctx, pedido_payload):
    pedido_payload["itens"] = []
    PedidoCriadoHandler(sf_service).handle(pedido_payload, ctx)
    fields = sf_service.upsert_opportunity_by_correlation.call_args.args[1]
    assert fields["Itens_Json__c"] == "[]"


def test_pedido_criado_truncates_huge_itens_json(sf_service, ctx, pedido_payload):
    # Gera array grande o bastante pra estourar 32768 chars
    pedido_payload["itens"] = [{"x": "a" * 100} for _ in range(1000)]
    PedidoCriadoHandler(sf_service).handle(pedido_payload, ctx)
    fields = sf_service.upsert_opportunity_by_correlation.call_args.args[1]
    assert len(fields["Itens_Json__c"]) <= 32768


def test_pedido_criado_update_when_service_says_not_created(sf_service, ctx, pedido_payload):
    sf_service.upsert_opportunity_by_correlation.return_value = {
        "id": None, "created": False, "success": True
    }
    result = PedidoCriadoHandler(sf_service).handle(pedido_payload, ctx)
    assert result.action is Action.ACK
