"""Testes de middleware.integrations.sap.session."""

from __future__ import annotations

import pytest

from middleware.integrations.sap.session import SapSession, SapSessionError


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for key in ("sessionId", "SAP_COMPANY_DB", "SG_SAP"):
        monkeypatch.delenv(key, raising=False)


def test_session_raises_when_token_missing():
    s = SapSession()
    with pytest.raises(SapSessionError, match="sessionId"):
        s.cookie_value()


def test_session_cookie_without_company_db(monkeypatch):
    monkeypatch.setenv("sessionId", "abc123")
    s = SapSession()
    assert s.cookie_value() == "B1SESSION=abc123"


def test_session_cookie_with_company_db(monkeypatch):
    monkeypatch.setenv("sessionId", "abc123")
    monkeypatch.setenv("SAP_COMPANY_DB", "SBODEMO")
    s = SapSession()
    assert s.cookie_value() == "B1SESSION=abc123; CompanyDB=SBODEMO"


def test_session_rereads_env_each_call(monkeypatch):
    """SapSession não deve cachear o token — o refresh no cluster é via env var."""
    monkeypatch.setenv("sessionId", "token-v1")
    s = SapSession()
    assert "token-v1" in s.cookie_value()

    monkeypatch.setenv("sessionId", "token-v2")
    assert "token-v2" in s.cookie_value()


def test_session_honors_custom_env_name(monkeypatch):
    monkeypatch.setenv("CUSTOM_TOKEN", "xyz")
    s = SapSession(token_env="CUSTOM_TOKEN")
    assert "xyz" in s.cookie_value()


def test_session_refresh_is_idempotent(monkeypatch):
    """refresh() só loga — próximo cookie_value relê env."""
    monkeypatch.setenv("sessionId", "first")
    s = SapSession()
    s.refresh()  # não deve lançar, não deve mudar nada
    assert "first" in s.cookie_value()
