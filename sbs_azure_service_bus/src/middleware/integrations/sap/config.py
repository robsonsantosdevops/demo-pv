"""Configuração do cliente SAP B1 Service Layer."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class SapConfig:
    base_url: str               # ex: https://host:50000/b1s/v2
    ssl_verify: bool
    timeout: int
    default_cardcode: str       # Business Partner default para Orders da demo
    default_item_code: str      # Item default (1 linha) para Orders da demo
    default_bpl_id: int         # Branch (BPL_IDAssignedToInvoice)

    @property
    def orders_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/Orders"

    @property
    def login_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/Login"


class SapConfigError(RuntimeError):
    pass


def _require(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise SapConfigError(f"Variável obrigatória ausente: {name}")
    return v


def load_sap_config() -> SapConfig:
    ssl_env = os.getenv("SSL_VERIFY", "false").strip().lower()
    ssl_verify = ssl_env not in ("false", "0", "no")

    return SapConfig(
        base_url=_require("SAP_BASE_URL"),
        ssl_verify=ssl_verify,
        timeout=int(os.getenv("SAP_HTTP_TIMEOUT", "30")),
        default_cardcode=os.getenv("SAP_DEFAULT_CARDCODE", "C40000"),
        default_item_code=os.getenv("SAP_DEFAULT_ITEM_CODE", "S10000"),
        default_bpl_id=int(os.getenv("SAP_DEFAULT_BPL_ID", "1")),
    )
