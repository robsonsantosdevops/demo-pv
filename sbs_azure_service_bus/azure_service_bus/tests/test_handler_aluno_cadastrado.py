"""Testes do handler aluno_cadastrado (publicado pelo checkout)."""

from __future__ import annotations

from middleware.handlers.aluno_cadastrado import AlunoCadastradoHandler
from middleware.handlers.base import Action


def test_aluno_happy_path(sf_service, ctx_aluno_cadastrado, aluno_cadastrado_payload):
    sf_service.upsert_contact_by_aluno_id.return_value = "003NEW"
    result = AlunoCadastradoHandler(sf_service).handle(
        aluno_cadastrado_payload, ctx_aluno_cadastrado
    )
    assert result.action is Action.ACK

    sf_service.ensure_account_master.assert_called_once()
    sf_service.upsert_contact_by_aluno_id.assert_called_once()
    kwargs = sf_service.upsert_contact_by_aluno_id.call_args.kwargs
    assert kwargs["aluno_id"] == 5
    assert kwargs["full_name"] == "Arya Stark"
    assert kwargs["email"] == "arya@win.test"
    assert kwargs["cpf"] == "12345678900"
    assert kwargs["telefone"] == "+5511988887777"


def test_aluno_missing_aluno_id_goes_to_dlq(
    sf_service, ctx_aluno_cadastrado, aluno_cadastrado_payload
):
    del aluno_cadastrado_payload["aluno_id"]
    result = AlunoCadastradoHandler(sf_service).handle(
        aluno_cadastrado_payload, ctx_aluno_cadastrado
    )
    assert result.action is Action.DLQ
    assert "aluno_id" in result.reason


def test_aluno_missing_nome_completo_goes_to_dlq(
    sf_service, ctx_aluno_cadastrado, aluno_cadastrado_payload
):
    del aluno_cadastrado_payload["nome_completo"]
    result = AlunoCadastradoHandler(sf_service).handle(
        aluno_cadastrado_payload, ctx_aluno_cadastrado
    )
    assert result.action is Action.DLQ
    assert "nome_completo" in result.reason


def test_aluno_missing_email_goes_to_dlq(
    sf_service, ctx_aluno_cadastrado, aluno_cadastrado_payload
):
    del aluno_cadastrado_payload["email"]
    result = AlunoCadastradoHandler(sf_service).handle(
        aluno_cadastrado_payload, ctx_aluno_cadastrado
    )
    assert result.action is Action.DLQ
    assert "email" in result.reason


def test_aluno_invalid_aluno_id_goes_to_dlq(
    sf_service, ctx_aluno_cadastrado, aluno_cadastrado_payload
):
    aluno_cadastrado_payload["aluno_id"] = "não-número"
    result = AlunoCadastradoHandler(sf_service).handle(
        aluno_cadastrado_payload, ctx_aluno_cadastrado
    )
    assert result.action is Action.DLQ
    assert "invalid_aluno_id" in result.reason


def test_aluno_empty_telefone_treated_as_absent(
    sf_service, ctx_aluno_cadastrado, aluno_cadastrado_payload
):
    """Checkout manda telefone: '' às vezes — não deve virar Phone vazio no SF."""
    aluno_cadastrado_payload["telefone"] = ""
    AlunoCadastradoHandler(sf_service).handle(
        aluno_cadastrado_payload, ctx_aluno_cadastrado
    )
    kwargs = sf_service.upsert_contact_by_aluno_id.call_args.kwargs
    assert kwargs["telefone"] is None


def test_aluno_empty_cpf_treated_as_absent(
    sf_service, ctx_aluno_cadastrado, aluno_cadastrado_payload
):
    aluno_cadastrado_payload["cpf"] = ""
    AlunoCadastradoHandler(sf_service).handle(
        aluno_cadastrado_payload, ctx_aluno_cadastrado
    )
    kwargs = sf_service.upsert_contact_by_aluno_id.call_args.kwargs
    assert kwargs["cpf"] is None


def test_aluno_correlation_id_optional_derives_default(
    sf_service, ctx_aluno_cadastrado, aluno_cadastrado_payload
):
    """correlation_id é opcional — handler deriva a partir de aluno_id + message_id."""
    # payload sem correlation_id (já é o default do fixture)
    assert "correlation_id" not in aluno_cadastrado_payload
    result = AlunoCadastradoHandler(sf_service).handle(
        aluno_cadastrado_payload, ctx_aluno_cadastrado
    )
    assert result.action is Action.ACK


def test_aluno_correlation_id_explicit_is_preserved(
    sf_service, ctx_aluno_cadastrado, aluno_cadastrado_payload
):
    """Se o checkout enviar correlation_id, ele é preservado (via log — aqui
    só checamos que não falha)."""
    aluno_cadastrado_payload["correlation_id"] = "jornada-custom-123"
    result = AlunoCadastradoHandler(sf_service).handle(
        aluno_cadastrado_payload, ctx_aluno_cadastrado
    )
    assert result.action is Action.ACK
