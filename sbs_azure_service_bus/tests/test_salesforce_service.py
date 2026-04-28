"""Testes do SalesforceService."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from middleware.integrations.salesforce.service import SalesforceService


@pytest.fixture
def sf_client():
    c = MagicMock()
    c.query.return_value = []
    return c


def test_ensure_account_master_creates_when_missing(sf_client, monkeypatch):
    monkeypatch.delenv("SF_ACCOUNT_MASTER_EXTRA", raising=False)
    sf_client.query.return_value = []
    sf_client.post.return_value = {"id": "001NEW"}

    svc = SalesforceService(sf_client)
    acc_id = svc.ensure_account_master("Master Alunos")
    assert acc_id == "001NEW"
    sf_client.post.assert_called_once_with("/sobjects/Account/", {"Name": "Master Alunos"})


def test_ensure_account_master_reuses_when_found(sf_client):
    sf_client.query.return_value = [{"Id": "001EXISTING"}]

    svc = SalesforceService(sf_client)
    acc_id = svc.ensure_account_master("Master Alunos")
    assert acc_id == "001EXISTING"
    sf_client.post.assert_not_called()


def test_ensure_account_master_is_cached(sf_client):
    sf_client.query.return_value = [{"Id": "001CACHED"}]
    svc = SalesforceService(sf_client)

    first = svc.ensure_account_master()
    second = svc.ensure_account_master()
    assert first == second
    # Query só na primeira chamada
    assert sf_client.query.call_count == 1


def test_ensure_account_master_merges_extra_fields(sf_client, monkeypatch):
    monkeypatch.setenv("SF_ACCOUNT_MASTER_EXTRA", '{"cnpj__c":"00000000000000"}')
    sf_client.query.return_value = []
    sf_client.post.return_value = {"id": "001NEW"}

    svc = SalesforceService(sf_client)
    svc.ensure_account_master("Master Alunos")
    payload = sf_client.post.call_args.args[1]
    assert payload["Name"] == "Master Alunos"
    assert payload["cnpj__c"] == "00000000000000"


def test_ensure_account_master_raises_on_invalid_extra_json(sf_client, monkeypatch):
    monkeypatch.setenv("SF_ACCOUNT_MASTER_EXTRA", "{invalid json}")
    sf_client.query.return_value = []
    svc = SalesforceService(sf_client)
    with pytest.raises(RuntimeError, match="não é JSON válido"):
        svc.ensure_account_master()


def test_upsert_contact_by_email_updates_existing(sf_client):
    sf_client.query.return_value = [{"Id": "003EXIST"}]
    svc = SalesforceService(sf_client)

    contact_id = svc.upsert_contact_by_email("001ACC", "Fulano Silva", "x@test.com")
    assert contact_id == "003EXIST"
    sf_client.patch.assert_called_once()
    sf_client.post.assert_not_called()


def test_upsert_contact_by_email_creates_when_missing(sf_client):
    sf_client.query.return_value = []
    sf_client.post.return_value = {"id": "003NEW"}

    svc = SalesforceService(sf_client)
    contact_id = svc.upsert_contact_by_email("001ACC", "Fulano Silva", "x@test.com")
    assert contact_id == "003NEW"
    payload = sf_client.post.call_args.args[1]
    assert payload["FirstName"] == "Fulano"
    assert payload["LastName"] == "Silva"
    assert payload["Email"] == "x@test.com"


def test_upsert_contact_single_name_goes_to_last_name(sf_client):
    sf_client.query.return_value = []
    sf_client.post.return_value = {"id": "003"}
    svc = SalesforceService(sf_client)
    svc.upsert_contact_by_email("001ACC", "Cher", "c@t.com")
    payload = sf_client.post.call_args.args[1]
    assert payload["LastName"] == "Cher"


def test_upsert_opportunity_by_correlation_strips_correlation_field(sf_client):
    sf_client.upsert_by_external.return_value = {
        "id": "006NEW", "created": True, "success": True
    }
    svc = SalesforceService(sf_client)

    fields = {
        "Name": "X",
        "Correlation_Id__c": "corr-1",  # deve ser removido (vai no path)
        "Amount": 100.0,
    }
    result = svc.upsert_opportunity_by_correlation("corr-1", fields)
    assert result["id"] == "006NEW"

    sent = sf_client.upsert_by_external.call_args.args[3]
    assert "Correlation_Id__c" not in sent
    assert sent["Name"] == "X"
    assert sent["Amount"] == 100.0


def test_find_opportunity_by_correlation_returns_first(sf_client):
    sf_client.query.return_value = [{"Id": "006A", "StageName": "Prospecting"}]
    svc = SalesforceService(sf_client)
    opp = svc.find_opportunity_by_correlation("corr-1")
    assert opp["Id"] == "006A"


def test_find_opportunity_by_correlation_returns_none_when_empty(sf_client):
    sf_client.query.return_value = []
    svc = SalesforceService(sf_client)
    assert svc.find_opportunity_by_correlation("corr-none") is None


def test_get_opportunity_by_id_requests_specific_fields(sf_client):
    sf_client.get.return_value = {"Name": "X", "Amount": 1.0}
    svc = SalesforceService(sf_client)
    res = svc.get_opportunity_by_id("006XYZ", fields=["Name", "Amount"])
    assert res == {"Name": "X", "Amount": 1.0}
    sf_client.get.assert_called_once_with(
        "/sobjects/Opportunity/006XYZ?fields=Name,Amount"
    )


def test_get_opportunity_by_id_returns_none_on_404(sf_client):
    sf_client.get.side_effect = LookupError("[404] not found")
    svc = SalesforceService(sf_client)
    assert svc.get_opportunity_by_id("006NOT_FOUND") is None


# ── SalesforceClient._request refresh-on-401 (unit) ────────────────────────


def test_client_refreshes_on_invalid_session_id():
    """Dado um 401 com INVALID_SESSION_ID, o client chama authenticate() e
    refaz a chamada. O caller só vê o sucesso."""
    from unittest.mock import MagicMock, patch

    from middleware.integrations.salesforce.client import SalesforceClient
    from middleware.integrations.salesforce.config import SalesforceConfig

    cfg = SalesforceConfig(
        username="u", password="p", security_token="t",
        consumer_key="", consumer_secret="",
        login_base="https://test.salesforce.com", api_version="v60.0", timeout=30,
    )
    client = SalesforceClient(cfg)
    client.instance_url = "https://x.salesforce.com"
    client.base_url = client.instance_url + cfg.base_path
    client.access_token = "old-token"

    expired_resp = MagicMock(
        status_code=401,
        text='[{"errorCode":"INVALID_SESSION_ID","message":"Session expired"}]',
    )
    ok_resp = MagicMock(status_code=200, content=b'{"records":[],"done":true}')
    ok_resp.json.return_value = {"records": [], "done": True}
    client.session.request = MagicMock(side_effect=[expired_resp, ok_resp])

    with patch.object(client, "authenticate") as auth:
        out = client.query("SELECT Id FROM Account LIMIT 1")

    assert out == []
    auth.assert_called_once()
    assert client.session.request.call_count == 2


# ── Contact by Aluno_Id__c ────────────────────────────────────────────────


def test_find_contact_by_aluno_id_found(sf_client):
    sf_client.query.return_value = [{"Id": "003ABC", "Email": "a@b.c", "Aluno_Id__c": 42}]
    svc = SalesforceService(sf_client)
    c = svc.find_contact_by_aluno_id(42)
    assert c["Id"] == "003ABC"


def test_find_contact_by_aluno_id_not_found(sf_client):
    sf_client.query.return_value = []
    svc = SalesforceService(sf_client)
    assert svc.find_contact_by_aluno_id(9999) is None


def test_upsert_contact_by_aluno_id_updates_match(sf_client):
    """Match por Aluno_Id__c → PATCH, sem POST."""
    sf_client.query.return_value = [{"Id": "003EXISTS", "Email": "x@y.z", "Aluno_Id__c": 5}]
    svc = SalesforceService(sf_client)
    out = svc.upsert_contact_by_aluno_id(
        "001ACC", 5, "Arya Stark", "arya@win.test", cpf="123", telefone="+5511"
    )
    assert out == "003EXISTS"
    sf_client.patch.assert_called_once()
    sf_client.post.assert_not_called()
    # Campos enviados no PATCH
    patched = sf_client.patch.call_args.args[1]
    assert patched["Aluno_Id__c"] == 5
    assert patched["CPF__c"] == "123"
    assert patched["Phone"] == "+5511"


def test_upsert_contact_by_aluno_id_upgrades_minimal_by_email(sf_client):
    """Sem match por Aluno_Id__c mas com Contact mínimo criado pelo fallback
    por email → PATCH enriquecendo e escrevendo Aluno_Id__c no existente."""
    sf_client.query.side_effect = [
        [],                              # find por aluno_id
        [{"Id": "003MIN"}],              # busca por email acha mínimo
    ]
    svc = SalesforceService(sf_client)
    out = svc.upsert_contact_by_aluno_id("001ACC", 7, "Jon Snow", "jon@wall.test")
    assert out == "003MIN"
    sf_client.patch.assert_called_once()
    sf_client.post.assert_not_called()


def test_upsert_contact_by_aluno_id_creates_when_both_miss(sf_client):
    sf_client.query.side_effect = [[], []]  # miss por aluno_id e por email
    sf_client.post.return_value = {"id": "003NEW"}
    svc = SalesforceService(sf_client)
    out = svc.upsert_contact_by_aluno_id("001ACC", 99, "New Guy", "new@t.c")
    assert out == "003NEW"
    payload = sf_client.post.call_args.args[1]
    assert payload["Aluno_Id__c"] == 99
    assert payload["Email"] == "new@t.c"


def test_upsert_contact_by_aluno_id_omits_none_optional_fields(sf_client):
    """cpf/telefone ausentes → chaves não vão no payload."""
    sf_client.query.side_effect = [[], []]
    sf_client.post.return_value = {"id": "003NEW"}
    svc = SalesforceService(sf_client)
    svc.upsert_contact_by_aluno_id("001ACC", 1, "X", "x@y.z")
    payload = sf_client.post.call_args.args[1]
    assert "CPF__c" not in payload
    assert "Phone" not in payload


# ── OpportunityContactRole idempotente ────────────────────────────────────


def test_ensure_ocr_creates_when_absent(sf_client):
    sf_client.query.return_value = []
    sf_client.post.return_value = {"id": "00KNEW"}
    svc = SalesforceService(sf_client)
    out = svc.ensure_opportunity_contact_role("006OPP", "003CON", "Aluno")
    assert out == "00KNEW"
    payload = sf_client.post.call_args.args[1]
    assert payload == {"OpportunityId": "006OPP", "ContactId": "003CON", "Role": "Aluno"}


def test_ensure_ocr_returns_existing_id(sf_client):
    sf_client.query.return_value = [{"Id": "00KEXIST"}]
    svc = SalesforceService(sf_client)
    out = svc.ensure_opportunity_contact_role("006OPP", "003CON")
    assert out == "00KEXIST"
    sf_client.post.assert_not_called()


def test_client_does_not_refresh_on_regular_401():
    """401 sem INVALID_SESSION_ID (ex.: profile sem permissão) NÃO tenta
    reautenticar — propaga a exceção pro caller."""
    from unittest.mock import MagicMock, patch

    import pytest

    from middleware.integrations.salesforce.client import SalesforceClient
    from middleware.integrations.salesforce.config import SalesforceConfig

    cfg = SalesforceConfig(
        username="u", password="p", security_token="t",
        consumer_key="", consumer_secret="",
        login_base="https://test.salesforce.com", api_version="v60.0", timeout=30,
    )
    client = SalesforceClient(cfg)
    client.instance_url = "https://x.salesforce.com"
    client.base_url = client.instance_url + cfg.base_path

    forbidden = MagicMock(status_code=401, text='[{"errorCode":"INSUFFICIENT_ACCESS"}]')
    client.session.request = MagicMock(return_value=forbidden)

    with patch.object(client, "authenticate") as auth, pytest.raises(PermissionError):
        client.get("/sobjects/Account/001x")
    auth.assert_not_called()
