"""Fixtures compartilhadas para todos os testes."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from middleware.handlers.base import HandlerContext


@pytest.fixture
def ctx() -> HandlerContext:
    """Contexto de handler padrão (pedidos/pedido_criado)."""
    return HandlerContext(
        queue="pedidos",
        tipo="pedido_criado",
        message_id="pedido_criado-1-abc",
        correlation_id="corr-001",
        delivery_count=0,
        traceparent=None,
    )


@pytest.fixture
def ctx_pagamento() -> HandlerContext:
    return HandlerContext(
        queue="pedidos",
        tipo="pagamento_aprovado",
        message_id="pagamento_aprovado-1-xyz",
        correlation_id="corr-001",
        delivery_count=0,
        traceparent=None,
    )


@pytest.fixture
def ctx_opp() -> HandlerContext:
    return HandlerContext(
        queue="oportunidades",
        tipo="oportunidade_ganha",
        message_id="oportunidade_ganha-1-zzz",
        correlation_id="sf-006OPP",
        delivery_count=0,
        traceparent=None,
    )


@pytest.fixture
def sf_service() -> MagicMock:
    """SalesforceService mockado com comportamento feliz default."""
    svc = MagicMock()
    svc.ensure_account_master.return_value = "001ACCOUNTMASTER"
    svc.upsert_contact_by_email.return_value = "003CONTACTMOCK"
    svc.upsert_contact_by_aluno_id.return_value = "003CONTACTMOCK"
    svc.find_contact_by_aluno_id.return_value = None
    svc.find_opportunity_by_name.return_value = None
    svc.find_opportunity_by_correlation.return_value = None
    svc.upsert_opportunity_by_correlation.return_value = {
        "id": "006OPPMOCK",
        "created": True,
        "success": True,
    }
    svc.ensure_opportunity_contact_role.return_value = "00KOCR"
    return svc


@pytest.fixture
def sap_client() -> MagicMock:
    """SapClient mockado com config embutida e comportamento feliz default."""
    client = MagicMock()
    client.config = MagicMock(
        base_url="https://sap.test/b1s/v2",
        default_cardcode="C40000",
        default_item_code="S10000",
        default_bpl_id=1,
    )
    # filter default: nenhuma Order existente (sem duplicata)
    client.get.return_value = {"value": []}
    client.create_order.return_value = {"DocEntry": 41000, "DocNum": 7000}
    return client


@pytest.fixture
def pedido_payload() -> dict:
    return {
        "correlation_id": "corr-001",
        "pedido_id": 42,
        "numero_pedido": "PED-TEST-001",
        "aluno_id": 7,
        "aluno_nome": "Fulano Teste",
        "aluno_email": "fulano@teste.com",
        "total": "199.90",
        "parcelas": 3,
        "status": "aguardando_pagamento",
        "itens": [
            {"curso_id": "c1", "curso_titulo": "Curso Um", "quantidade": 1, "preco_unitario": 199.9}
        ],
        "created_at": "2026-04-23T00:00:00.000Z",
    }


@pytest.fixture
def pagamento_payload() -> dict:
    return {
        "correlation_id": "corr-001",
        "pagamento_id": 99,
        "protocolo": "PAG-TEST-001",
        "pedido_id": 42,
        "numero_pedido": "PED-TEST-001",
        "aluno_id": 7,
        "aluno_nome": "Fulano Teste",
        "aluno_email": "fulano@teste.com",
        "forma_pagamento": "pix",
        "valor": "199.90",
        "parcelas": 3,
        "status_pagamento": "aprovado",
        "status_pedido": "pago",
        "cartao_final": None,
        "created_at": "2026-04-23T00:00:05.000Z",
    }


@pytest.fixture
def ctx_aluno_cadastrado() -> HandlerContext:
    return HandlerContext(
        queue="contatos",
        tipo="aluno_cadastrado",
        message_id="aluno_cadastrado-1-aaa",
        correlation_id=None,  # opcional no contrato oficial do checkout
        delivery_count=0,
        traceparent=None,
    )


@pytest.fixture
def aluno_cadastrado_payload() -> dict:
    """Payload canônico enviado pelo checkout (POC)."""
    return {
        "aluno_id": 5,
        "nome_completo": "Arya Stark",
        "email": "arya@win.test",
        "cpf": "12345678900",
        "telefone": "+5511988887777",
        "created_at": "2026-04-23T15:00:00.000Z",
    }


@pytest.fixture
def ctx_relatorio() -> HandlerContext:
    return HandlerContext(
        queue="relatorios",
        tipo="pedido_report",
        message_id="pedido_report-1-xxx",
        correlation_id="corr-rel-001",
        delivery_count=0,
        traceparent=None,
    )


@pytest.fixture
def pedido_report_payload() -> dict:
    return {
        "correlation_id": "corr-rel-001",
        "opportunity_id": "006TEST01",
        "opportunity_name": "PED-17",
        "account_id": "001TESTACC",
        "relatorio_sap_id": "a01RELATORIO",
        "requested_by_user_id": "005USER",
        "requested_at": "2026-04-24T19:13:33.493Z",
    }


@pytest.fixture
def sap_order_fixture() -> dict:
    """Representa uma Order do SAP com UDFs e linhas."""
    return {
        "DocEntry": 41367, "DocNum": 7434,
        "DocDate": "2026-04-23T00:00:00Z",
        "DocDueDate": "2026-05-23T00:00:00Z",
        "DocTotal": 12990.0,
        "DocumentStatus": "bost_Open",
        "CardCode": "C40000",
        "NumAtCard": "006TEST01",
        "Comments": "Opp: PED-17 (006TEST01)",
        "U_SF_OppId": "006TEST01",
        "U_SF_OppName": "PED-17",
        "U_Curso_Nome": "Enem Online",
        "U_Aluno_Nome": "Fulano",
        "DocumentLines": [
            {"LineNum": 0, "ItemCode": "S10000", "Quantity": 1.0,
             "UnitPrice": 12990.0, "LineTotal": 12990.0},
        ],
    }


@pytest.fixture
def opp_payload() -> dict:
    return {
        "correlation_id": "sf-006OPP",
        "opportunity_id": "006OPP12345",
        "name": "SB Test Opp",
        "amount": 1500.0,
        "close_date": "2026-12-31",
        "account_id": "001ACC999",
        "owner_id": "005OWN999",
    }
