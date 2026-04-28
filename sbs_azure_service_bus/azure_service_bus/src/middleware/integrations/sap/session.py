"""Session provider para SAP B1 Service Layer.

No cluster Kubernetes demo, a env var `sessionId` (nome exato, case-sensitive)
é atualizada por um job externo a cada ~30min com um B1SESSION fresco. Este
módulo abstrai essa leitura:

- `cookie_value()` retorna a string completa do header Cookie para cada request.
- `refresh()` força uma re-leitura do env (útil quando o client recebe 401).

Não fazemos cache estático do token. Se o deploy futuramente passar a
obter o token via SDK Kubernetes ou via `POST /Login` próprio, basta
trocar esta classe sem mexer no client.
"""

from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)


class SapSessionError(RuntimeError):
    pass


class SapSession:
    """Envolve a leitura do session token + CompanyDB a partir do env."""

    def __init__(
        self,
        token_env: str = "sessionId",
        company_db_env: str = "SAP_COMPANY_DB",
    ) -> None:
        self._token_env = token_env
        self._company_db_env = company_db_env

    def _token(self) -> str:
        v = os.environ.get(self._token_env, "").strip()
        if not v:
            raise SapSessionError(
                f"{self._token_env} vazio/ausente no ambiente — session SAP indisponível"
            )
        return v

    def _company_db(self) -> str:
        return os.environ.get(self._company_db_env, "").strip()

    def cookie_value(self) -> str:
        """Retorna a string completa do header Cookie."""
        parts = [f"B1SESSION={self._token()}"]
        company_db = self._company_db()
        if company_db:
            parts.append(f"CompanyDB={company_db}")
        return "; ".join(parts)

    def refresh(self) -> None:
        """No cluster, o env já pode ter sido atualizado. Só logamos para
        dar visibilidade; a próxima chamada a cookie_value() relê."""
        log.info(
            "sap session refresh solicitada — relê sessionId no próximo request",
            extra={"status": "refresh"},
        )
