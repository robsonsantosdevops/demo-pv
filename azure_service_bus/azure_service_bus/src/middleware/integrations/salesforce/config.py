"""Configuração do cliente Salesforce. Lida a partir do env do middleware."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class SalesforceConfig:
    username: str
    password: str
    security_token: str
    consumer_key: str
    consumer_secret: str
    domain: str              # "login" (prod) | "test" (sandbox)
    api_version: str         # e.g. "v60.0"
    timeout: int

    @property
    def login_url(self) -> str:
        return f"https://{self.domain}.salesforce.com"

    @property
    def base_path(self) -> str:
        return f"/services/data/{self.api_version}"


class SalesforceConfigError(RuntimeError):
    pass


def _require(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise SalesforceConfigError(f"Variável obrigatória ausente: {name}")
    return v


def load_salesforce_config() -> SalesforceConfig:
    """Carrega SF_* do env. Exige username/password/security_token."""
    domain = os.getenv("SF_DOMAIN", "test").strip()  # default sandbox
    # Aceita tb SF_LOGIN_URL=https://test.salesforce.com
    login_url = os.getenv("SF_LOGIN_URL", "").strip()
    if login_url:
        # Deriva domain do login_url: "https://test.salesforce.com" → "test"
        without_scheme = login_url.replace("https://", "").replace("http://", "")
        domain = without_scheme.split(".", 1)[0]

    return SalesforceConfig(
        username=_require("SF_USERNAME"),
        password=_require("SF_PASSWORD"),
        security_token=_require("SF_SECURITY_TOKEN"),
        consumer_key=os.getenv("SF_CONSUMER_KEY", ""),
        consumer_secret=os.getenv("SF_CONSUMER_SECRET", ""),
        domain=domain,
        api_version=os.getenv("SF_API_VERSION", "v60.0"),
        timeout=int(os.getenv("SF_HTTP_TIMEOUT", "30")),
    )
