"""Cliente HTTP para SAP B1 Service Layer.

Derivado de sap-automation-lab/src/sap_client.py — ver ORIGIN.md. Difere
do original em:
- Session token vem via SapSession (dinâmico), não armazenado no client.
- Retry automático em 401 (sessão expirada): re-lê env e refaz 1x.
- Config via SapConfig.
"""

from __future__ import annotations

import logging
import warnings
from typing import Any

import requests
from urllib3.exceptions import InsecureRequestWarning

from middleware.integrations.sap.config import SapConfig
from middleware.integrations.sap.session import SapSession

log = logging.getLogger(__name__)


class SapClient:
    def __init__(self, config: SapConfig, session: SapSession) -> None:
        self.config = config
        self.session = session
        if not config.ssl_verify:
            warnings.filterwarnings("ignore", category=InsecureRequestWarning)

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Cookie": self.session.cookie_value(),
        }

    def _is_expired_session(self, resp: requests.Response) -> bool:
        if resp.status_code != 401:
            return False
        # SAP B1 devolve 401 com mensagem contendo "Invalid session" ou similar.
        # Não tentamos distinguir — qualquer 401 é suficiente pra pedir refresh.
        return True

    def _request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        headers = self._headers()
        extra_headers = kwargs.pop("headers", None)
        if extra_headers:
            headers.update(extra_headers)

        resp = requests.request(
            method=method,
            url=url,
            headers=headers,
            timeout=self.config.timeout,
            verify=self.config.ssl_verify,
            **kwargs,
        )

        if self._is_expired_session(resp):
            log.warning(
                "sap 401 — tentando refresh e reenviando uma vez",
                extra={"status": "retry_after_401", "reason": url},
            )
            self.session.refresh()
            resp = requests.request(
                method=method,
                url=url,
                headers=self._headers(),  # relê cookie atualizado
                timeout=self.config.timeout,
                verify=self.config.ssl_verify,
                **kwargs,
            )

        return resp

    # ── HTTP ────────────────────────────────────────────────────────────────

    def get(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        resp = self._request("GET", url, params=params)
        resp.raise_for_status()
        return resp.json()

    def post(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        resp = self._request("POST", url, json=payload)
        resp.raise_for_status()
        return resp.json()

    # ── Operações de alto nível ─────────────────────────────────────────────

    def create_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        """POST /b1s/v2/Orders. Retorna o Order JSON (com DocEntry/DocNum)."""
        return self.post(self.config.orders_url, payload)

    def find_order_by_numatcard(self, opp_id: str) -> dict[str, Any] | None:
        """Busca Order usando o NumAtCard (convenção do middleware: NumAtCard = OppId SF).

        Estratégia em 2 passos pra evitar depender de `$expand`:
          1. filter pelo `NumAtCard` pra obter DocEntry;
          2. GET /Orders(<DocEntry>) pra trazer o objeto completo com DocumentLines.
        Retorna o Order completo ou None se não houver match.
        """
        escaped = opp_id.replace("'", "''")
        search = (
            f"{self.config.orders_url}"
            f"?$filter=NumAtCard eq '{escaped}'&$select=DocEntry&$top=1"
        )
        resp = self.get(search)
        values = resp.get("value") or []
        if not values:
            return None
        doc_entry = values[0]["DocEntry"]
        return self.get(f"{self.config.orders_url}({doc_entry})")
