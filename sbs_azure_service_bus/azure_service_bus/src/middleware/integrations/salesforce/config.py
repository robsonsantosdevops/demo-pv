"""Configuração do cliente Salesforce. Lida a partir do env do middleware."""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True)
class SalesforceConfig:
    username: str
    password: str
    security_token: str
    consumer_key: str
    consumer_secret: str
    #: Host de autenticação OAuth/SOAP (ex.: https://test.salesforce.com ou
    #: https://minha-org.my.salesforce.com para My Domain — não use *.lightning.force.com).
    login_base: str
    api_version: str         # e.g. "v60.0"
    timeout: int

    @property
    def login_url(self) -> str:
        return self.login_base

    @property
    def base_path(self) -> str:
        return f"/services/data/{self.api_version}"


class SalesforceConfigError(RuntimeError):
    pass


def _require(name: str) -> str:
    v = os.getenv(name)
    if v is None:
        raise SalesforceConfigError(f"Variável obrigatória ausente: {name}")
    v = v.strip()
    if not v:
        raise SalesforceConfigError(f"Variável obrigatória vazia (após trim): {name}")
    return v


def _normalize_login_base(url: str) -> str:
    """Extrai scheme://host para OAuth/SOAP (sem path). Aceita My Domain completo."""
    raw = url.strip().rstrip("/")
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise SalesforceConfigError(f"SF_LOGIN_URL inválida: {url!r}")
    return f"{parsed.scheme}://{parsed.netloc}"


def load_salesforce_config() -> SalesforceConfig:
    """Carrega SF_* do env. Exige username/password/security_token.

    SF_LOGIN_URL pode ser:
    - https://test.salesforce.com (sandbox clássico)
    - https://login.salesforce.com (produção)
    - https://<my-domain>.my.salesforce.com (My Domain — recomendado para DE/sandbox com domínio próprio)

    Não use URLs *.lightning.force.com; o token OAuth fica em .../services/oauth2/token no host my.salesforce.com.
    """
    login_env = os.getenv("SF_LOGIN_URL", "").strip()
    if login_env:
        login_base = _normalize_login_base(login_env)
    else:
        domain = os.getenv("SF_DOMAIN", "test").strip()
        login_base = f"https://{domain}.salesforce.com"

    return SalesforceConfig(
        username=_require("SF_USERNAME"),
        password=_require("SF_PASSWORD"),
        security_token=_require("SF_SECURITY_TOKEN"),
        consumer_key=os.getenv("SF_CONSUMER_KEY", ""),
        consumer_secret=os.getenv("SF_CONSUMER_SECRET", ""),
        login_base=login_base,
        api_version=os.getenv("SF_API_VERSION", "v60.0"),
        timeout=int(os.getenv("SF_HTTP_TIMEOUT", "30")),
    )
