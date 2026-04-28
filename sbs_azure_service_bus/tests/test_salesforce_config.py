"""Testes de load_salesforce_config (URL de login / My Domain)."""

from __future__ import annotations

import pytest

from middleware.integrations.salesforce.config import (
    SalesforceConfigError,
    load_salesforce_config,
)


@pytest.fixture(autouse=True)
def _clean_sf_env(monkeypatch):
    for key in (
        "SF_USERNAME",
        "SF_PASSWORD",
        "SF_SECURITY_TOKEN",
        "SF_CONSUMER_KEY",
        "SF_CONSUMER_SECRET",
        "SF_LOGIN_URL",
        "SF_DOMAIN",
        "SF_API_VERSION",
        "SF_HTTP_TIMEOUT",
    ):
        monkeypatch.delenv(key, raising=False)


def test_login_base_default_domain_test(monkeypatch):
    monkeypatch.setenv("SF_USERNAME", "u")
    monkeypatch.setenv("SF_PASSWORD", "p")
    monkeypatch.setenv("SF_SECURITY_TOKEN", "t")
    cfg = load_salesforce_config()
    assert cfg.login_base == "https://test.salesforce.com"


def test_login_base_from_sf_domain(monkeypatch):
    monkeypatch.setenv("SF_USERNAME", "u")
    monkeypatch.setenv("SF_PASSWORD", "p")
    monkeypatch.setenv("SF_SECURITY_TOKEN", "t")
    monkeypatch.setenv("SF_DOMAIN", "login")
    cfg = load_salesforce_config()
    assert cfg.login_base == "https://login.salesforce.com"


def test_login_base_full_my_domain(monkeypatch):
    monkeypatch.setenv("SF_USERNAME", "u")
    monkeypatch.setenv("SF_PASSWORD", "p")
    monkeypatch.setenv("SF_SECURITY_TOKEN", "t")
    monkeypatch.setenv(
        "SF_LOGIN_URL",
        "https://demo-keeggo-dev-ed.develop.my.salesforce.com/lightning",
    )
    cfg = load_salesforce_config()
    assert cfg.login_base == "https://demo-keeggo-dev-ed.develop.my.salesforce.com"


def test_login_base_strips_path(monkeypatch):
    monkeypatch.setenv("SF_USERNAME", "u")
    monkeypatch.setenv("SF_PASSWORD", "p")
    monkeypatch.setenv("SF_SECURITY_TOKEN", "t")
    monkeypatch.setenv("SF_LOGIN_URL", "https://test.salesforce.com/")
    cfg = load_salesforce_config()
    assert cfg.login_base == "https://test.salesforce.com"


def test_login_url_invalid_raises(monkeypatch):
    monkeypatch.setenv("SF_USERNAME", "u")
    monkeypatch.setenv("SF_PASSWORD", "p")
    monkeypatch.setenv("SF_SECURITY_TOKEN", "t")
    monkeypatch.setenv("SF_LOGIN_URL", "http://")
    with pytest.raises(SalesforceConfigError, match="SF_LOGIN_URL"):
        load_salesforce_config()
