"""Cliente HTTP para a Salesforce REST API.

Derivado de salesforce-admin/client.py — ver ORIGIN.md. Diferenças:
- Config injetada no construtor (não global)
- Logger stdlib (`logging.getLogger(__name__)`)
Resto da API e estratégias de autenticação são idênticos ao original.
"""

from __future__ import annotations

import logging
from urllib.parse import quote

import requests  # noqa: I001

from middleware.integrations.salesforce.config import SalesforceConfig

log = logging.getLogger(__name__)


class SalesforceClient:
    """Cliente HTTP genérico para a Salesforce REST API."""

    def __init__(self, config: SalesforceConfig) -> None:
        self.config = config
        self.instance_url: str = ""
        self.base_url: str = ""
        self.access_token: str = ""
        self.session = requests.Session()
        self.session.headers.update(
            {"Content-Type": "application/json", "Accept": "application/json"}
        )

    # ── Autenticação ────────────────────────────────────────────────────────

    def authenticate(self) -> None:
        """Autentica tentando (1) OAuth2 user/pwd com consumer key, (2) SOAP,
        (3) OAuth2 com client_ids conhecidos do Salesforce CLI."""
        if self.config.consumer_key and self.config.consumer_secret:
            self._auth_oauth2()
        else:
            try:
                self._auth_soap()
            except PermissionError:
                log.info("SOAP login indisponível, tentando OAuth2 (Salesforce CLI)")
                self._auth_oauth2_cli()

        self.base_url = f"{self.instance_url}{self.config.base_path}"
        self.session.headers["Authorization"] = f"Bearer {self.access_token}"
        log.info("autenticado", extra={"status": "ok", "reason": self.instance_url})

    def _auth_oauth2(self) -> None:
        url = f"{self.config.login_url}/services/oauth2/token"
        payload = {
            "grant_type": "password",
            "client_id": self.config.consumer_key,
            "client_secret": self.config.consumer_secret,
            "username": self.config.username,
            "password": self.config.password + self.config.security_token,
        }
        resp = requests.post(url, data=payload, timeout=self.config.timeout)
        if resp.status_code != 200:
            raise PermissionError(f"OAuth2 falhou ({resp.status_code}): {resp.text}")
        data = resp.json()
        self.access_token = data["access_token"]
        self.instance_url = data["instance_url"]

    def _auth_oauth2_cli(self) -> None:
        url = f"{self.config.login_url}/services/oauth2/token"
        client_ids = ["PlatformCLI", "SalesforceDevelopmentExperience"]
        last_error = ""
        for client_id in client_ids:
            payload = {
                "grant_type": "password",
                "client_id": client_id,
                "username": self.config.username,
                "password": self.config.password + self.config.security_token,
            }
            resp = requests.post(url, data=payload, timeout=self.config.timeout)
            if resp.status_code == 200:
                data = resp.json()
                self.access_token = data["access_token"]
                self.instance_url = data["instance_url"]
                return
            last_error = resp.text
        raise PermissionError(f"OAuth2 falhou com todos os client_ids: {last_error}")

    def _auth_soap(self) -> None:
        url = f"{self.config.login_url}/services/Soap/u/59.0"
        soap_body = f"""<?xml version="1.0" encoding="utf-8" ?>
<env:Envelope xmlns:xsd="http://www.w3.org/2001/XMLSchema"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xmlns:env="http://schemas.xmlsoap.org/soap/envelope/">
  <env:Body>
    <n1:login xmlns:n1="urn:partner.soap.sforce.com">
      <n1:username>{self.config.username}</n1:username>
      <n1:password>{self.config.password}{self.config.security_token}</n1:password>
    </n1:login>
  </env:Body>
</env:Envelope>"""
        headers = {"Content-Type": "text/xml; charset=utf-8", "SOAPAction": "login"}
        resp = requests.post(url, data=soap_body, headers=headers, timeout=self.config.timeout)
        if resp.status_code != 200:
            raise PermissionError(f"SOAP login falhou ({resp.status_code}): {resp.text}")
        body = resp.text
        self.access_token = body.split("<sessionId>")[1].split("</sessionId>")[0]
        server_url = body.split("<serverUrl>")[1].split("</serverUrl>")[0]
        self.instance_url = server_url.split("/services/")[0]

    # ── URL builder ─────────────────────────────────────────────────────────

    def _full_url(self, path: str) -> str:
        if path.startswith("http"):
            return path
        if path.startswith("/services/"):
            return f"{self.instance_url}{path}"
        return f"{self.base_url}{path}"

    # ── HTTP (com refresh-on-401) ──────────────────────────────────────────

    def _is_expired_session(self, resp: requests.Response) -> bool:
        """401 com INVALID_SESSION_ID = access token SF expirou (TTL ~2h).

        Detectamos pelo código do SF, não só pelo HTTP status, pra não
        confundir com 401 "profile sem permissão" (outra coisa).
        """
        if resp.status_code != 401:
            return False
        body = resp.text or ""
        return "INVALID_SESSION_ID" in body

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        """Wrapper comum: se receber 401 INVALID_SESSION_ID, reautentica e
        refaz a chamada uma vez. Caller ainda aplica `_handle_error` no
        resultado final."""
        url = self._full_url(path)
        timeout = kwargs.pop("timeout", self.config.timeout)
        resp = self.session.request(method, url, timeout=timeout, **kwargs)
        if self._is_expired_session(resp):
            log.warning(
                "sf 401 INVALID_SESSION_ID — reautenticando e reenviando 1x",
                extra={"status": "retry_after_401", "reason": path},
            )
            self.authenticate()
            # base_url pode ter mudado se instance_url mudou; recalcula
            url = self._full_url(path)
            resp = self.session.request(method, url, timeout=timeout, **kwargs)
        return resp

    def get(self, path: str, **kwargs) -> dict:
        resp = self._request("GET", path, **kwargs)
        self._handle_error(resp)
        return resp.json()

    def post(self, path: str, data: dict, **kwargs) -> dict:
        resp = self._request("POST", path, json=data, **kwargs)
        self._handle_error(resp)
        return resp.json()

    def patch(self, path: str, data: dict, **kwargs) -> dict | None:
        resp = self._request("PATCH", path, json=data, **kwargs)
        self._handle_error(resp)
        if resp.status_code == 204 or not resp.content:
            return None
        return resp.json()

    def upsert_by_external(
        self, sobject: str, external_field: str, external_value: str, payload: dict
    ) -> dict:
        """PATCH /sobjects/<sobject>/<external_field>/<external_value>

        Idempotente: cria se não existir, atualiza se existir. O SF resolve pela
        unicidade do external_field. Retorna dict com {id, created, success}.
        Quando só atualiza, SF devolve 204 (sem id no body) — nesse caso, o id
        não é incluído no retorno.
        """
        path = f"/sobjects/{sobject}/{external_field}/{quote(str(external_value), safe='')}"
        resp = self._request("PATCH", path, json=payload)
        self._handle_error(resp)
        if resp.status_code == 204 or not resp.content:
            return {"created": False, "success": True}
        data = resp.json()
        return {
            "id": data.get("id"),
            "created": data.get("created", False),
            "success": data.get("success", True),
        }

    def delete(self, path: str, **kwargs) -> None:
        resp = self._request("DELETE", path, **kwargs)
        self._handle_error(resp)

    # ── Helpers ─────────────────────────────────────────────────────────────

    def query(self, soql: str) -> list[dict]:
        encoded = quote(soql, safe="")
        path = f"/query/?q={encoded}"
        all_records: list[dict] = []
        while True:
            resp = self._request("GET", path)
            self._handle_error(resp)
            data = resp.json()
            for r in data.get("records", []):
                r.pop("attributes", None)
                all_records.append(r)
            if data.get("done", True):
                break
            # nextRecordsUrl já vem como /services/data/... ou URL completa
            path = data["nextRecordsUrl"]
        return all_records

    def describe(self, sobject: str) -> dict:
        return self.get(f"/sobjects/{sobject}/describe/")

    # ── Errors ──────────────────────────────────────────────────────────────

    @staticmethod
    def _handle_error(response: requests.Response) -> None:
        status = response.status_code
        if 200 <= status < 300:
            return
        try:
            errors = response.json()
            if isinstance(errors, list) and errors:
                msg = f"{errors[0].get('errorCode', 'UNKNOWN')}: {errors[0].get('message', '')}"
            elif isinstance(errors, dict):
                msg = errors.get("message", response.text)
            else:
                msg = response.text
        except Exception:  # noqa: BLE001
            msg = response.text

        if status == 401:
            raise PermissionError(f"[401] {msg}")
        if status == 400:
            raise ValueError(f"[400] {msg}")
        if status == 404:
            raise LookupError(f"[404] {msg}")
        if status == 403:
            raise PermissionError(f"[403] {msg}")
        raise RuntimeError(f"[{status}] {msg}")
