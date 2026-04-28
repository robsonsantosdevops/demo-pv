"""Operações de alto nível sobre o Salesforce, acima do client HTTP.

Este service é deliberadamente enxuto: só cobre o que os handlers do
middleware usam hoje (Account master, Contact por email, Opportunity por
Name). Campos custom e lookups mais ricos ficam para evoluções futuras.
"""

from __future__ import annotations

import json
import logging
import os

from middleware.integrations.salesforce.client import SalesforceClient

log = logging.getLogger(__name__)

ACCOUNT_MASTER_NAME = "Checkout Keeggo - Alunos"


def _account_master_extra() -> dict:
    """Campos obrigatórios específicos da org (ex.: cnpj__c na demo Keeggo).

    Valor via env var SF_ACCOUNT_MASTER_EXTRA como JSON:
        SF_ACCOUNT_MASTER_EXTRA={"cnpj__c": "00000000000000"}
    """
    raw = os.getenv("SF_ACCOUNT_MASTER_EXTRA", "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"SF_ACCOUNT_MASTER_EXTRA não é JSON válido: {e}") from e
    if not isinstance(parsed, dict):
        raise RuntimeError("SF_ACCOUNT_MASTER_EXTRA precisa ser objeto JSON")
    return parsed


def _soql_escape(s: str) -> str:
    """Escape mínimo de SOQL string literal."""
    return s.replace("\\", "\\\\").replace("'", "\\'")


def _split_name(full: str) -> tuple[str | None, str]:
    """Divide um nome completo em (FirstName, LastName). LastName é obrigatório no SF."""
    parts = full.strip().split(None, 1)
    if len(parts) == 1:
        return None, parts[0] or "N/D"
    return parts[0], parts[1]


class SalesforceService:
    def __init__(self, client: SalesforceClient) -> None:
        self.client = client
        self._account_master_id: str | None = None

    # ── Account ─────────────────────────────────────────────────────────────

    def ensure_account_master(self, name: str = ACCOUNT_MASTER_NAME) -> str:
        """Garante a Account 'master' para alunos do checkout. Idempotente.
        Faz cache em memória para não buscar a cada mensagem."""
        if self._account_master_id:
            return self._account_master_id

        found = self.client.query(
            f"SELECT Id FROM Account WHERE Name = '{_soql_escape(name)}' LIMIT 1"
        )
        if found:
            self._account_master_id = found[0]["Id"]
            log.info("account master encontrada", extra={"reason": self._account_master_id})
            return self._account_master_id

        payload = {"Name": name, **_account_master_extra()}
        created = self.client.post("/sobjects/Account/", payload)
        self._account_master_id = created["id"]
        log.info("account master criada", extra={"reason": self._account_master_id})
        return self._account_master_id

    # ── Contact ─────────────────────────────────────────────────────────────

    def upsert_contact_by_email(
        self, account_id: str, full_name: str, email: str
    ) -> str:
        """Cria ou atualiza Contact identificado por Email. Retorna o Id.

        Usado como fallback pelo handler pedido_criado quando o Contact
        ainda não foi criado pelo handler aluno_cadastrado (ordem invertida).
        """
        first, last = _split_name(full_name)
        rec = self.client.query(
            f"SELECT Id FROM Contact WHERE Email = '{_soql_escape(email)}' LIMIT 1"
        )
        if rec:
            contact_id = rec[0]["Id"]
            self.client.patch(
                f"/sobjects/Contact/{contact_id}",
                {"FirstName": first or "", "LastName": last, "AccountId": account_id},
            )
            return contact_id

        payload = {
            "FirstName": first or "",
            "LastName": last,
            "Email": email,
            "AccountId": account_id,
        }
        created = self.client.post("/sobjects/Contact/", payload)
        return created["id"]

    def find_contact_by_aluno_id(self, aluno_id: int) -> dict | None:
        """Match primário de Contact — por External ID Aluno_Id__c."""
        rec = self.client.query(
            f"SELECT Id, Email, Aluno_Id__c FROM Contact "
            f"WHERE Aluno_Id__c = {int(aluno_id)} LIMIT 1"
        )
        return rec[0] if rec else None

    def upsert_contact_by_aluno_id(
        self,
        account_id: str,
        aluno_id: int,
        full_name: str,
        email: str,
        cpf: str | None = None,
        telefone: str | None = None,
    ) -> str:
        """Cria ou atualiza Contact identificado por Aluno_Id__c.

        Estratégia:
          1. find_contact_by_aluno_id — match canônico.
          2. Se não encontrar, tenta match por email (Contact mínimo criado
             antes pelo fallback do pedido_criado) e faz "upgrade" preenchendo
             Aluno_Id__c + campos novos.
          3. Se não encontrar por nenhum, cria Contact novo.
        """
        first, last = _split_name(full_name)
        fields: dict = {
            "FirstName": first or "",
            "LastName": last,
            "Email": email,
            "AccountId": account_id,
            "Aluno_Id__c": int(aluno_id),
        }
        if cpf:
            fields["CPF__c"] = cpf
        if telefone:
            fields["Phone"] = telefone

        # 1) match por Aluno_Id__c
        existing = self.find_contact_by_aluno_id(aluno_id)
        if existing:
            self.client.patch(f"/sobjects/Contact/{existing['Id']}", fields)
            return existing["Id"]

        # 2) match por email (Contact mínimo criado pelo fallback do pedido)
        by_email = self.client.query(
            f"SELECT Id FROM Contact WHERE Email = '{_soql_escape(email)}' LIMIT 1"
        )
        if by_email:
            contact_id = by_email[0]["Id"]
            self.client.patch(f"/sobjects/Contact/{contact_id}", fields)
            return contact_id

        # 3) cria novo
        created = self.client.post("/sobjects/Contact/", fields)
        return created["id"]

    # ── Relatorio_SAP__c ────────────────────────────────────────────────────

    def update_relatorio_sap(self, relatorio_id: str, **fields) -> None:
        """PATCH no Relatorio_SAP__c. Null-strips o payload."""
        clean = {k: v for k, v in fields.items() if v is not None}
        if not clean:
            return
        self.client.patch(f"/sobjects/Relatorio_SAP__c/{relatorio_id}", clean)

    def mark_relatorio_erro(self, relatorio_id: str, mensagem: str) -> None:
        """Atalho: Status='Erro' + Mensagem_Erro__c + Data_Recebimento__c=now."""
        from datetime import datetime, timezone
        self.update_relatorio_sap(
            relatorio_id,
            Status__c="Erro",
            Mensagem_Erro__c=mensagem[:32000],
            Data_Recebimento__c=datetime.now(timezone.utc)
                .isoformat(timespec="seconds").replace("+00:00", "Z"),
        )

    def replace_relatorio_sap_linhas(
        self, relatorio_id: str, linhas: list[dict]
    ) -> int:
        """Apaga todas as Relatorio_SAP_Linha__c existentes do relatorio e insere as novas.

        Retorna a quantidade inserida.
        """
        # Busca linhas atuais
        existing = self.client.query(
            "SELECT Id FROM Relatorio_SAP_Linha__c "
            f"WHERE Relatorio_SAP__c = '{_soql_escape(relatorio_id)}'"
        )
        for rec in existing:
            self.client.delete(f"/sobjects/Relatorio_SAP_Linha__c/{rec['Id']}")

        for linha in linhas:
            payload = {"Relatorio_SAP__c": relatorio_id, **linha}
            self.client.post("/sobjects/Relatorio_SAP_Linha__c/", payload)
        return len(linhas)

    # ── OpportunityContactRole ──────────────────────────────────────────────

    def ensure_opportunity_contact_role(
        self, opportunity_id: str, contact_id: str, role: str = "Aluno"
    ) -> str:
        """Cria OpportunityContactRole(Opp, Contact, role) se ainda não existir.
        Idempotente — retorna o Id do registro (novo ou existente)."""
        rec = self.client.query(
            "SELECT Id FROM OpportunityContactRole "
            f"WHERE OpportunityId = '{_soql_escape(opportunity_id)}' "
            f"AND ContactId = '{_soql_escape(contact_id)}' LIMIT 1"
        )
        if rec:
            return rec[0]["Id"]
        created = self.client.post(
            "/sobjects/OpportunityContactRole/",
            {"OpportunityId": opportunity_id, "ContactId": contact_id, "Role": role},
        )
        return created["id"]

    # ── Opportunity ─────────────────────────────────────────────────────────

    OPP_FIELDS_SELECT = (
        "Id, Name, StageName, Amount, CloseDate, Description, Correlation_Id__c"
    )

    def find_opportunity_by_name(self, name: str) -> dict | None:
        rec = self.client.query(
            f"SELECT {self.OPP_FIELDS_SELECT} "
            f"FROM Opportunity WHERE Name = '{_soql_escape(name)}' LIMIT 1"
        )
        return rec[0] if rec else None

    def find_opportunity_by_correlation(self, correlation_id: str) -> dict | None:
        rec = self.client.query(
            f"SELECT {self.OPP_FIELDS_SELECT} "
            f"FROM Opportunity WHERE Correlation_Id__c = '{_soql_escape(correlation_id)}' LIMIT 1"
        )
        return rec[0] if rec else None

    def get_opportunity_by_id(
        self, opportunity_id: str, fields: list[str] | None = None
    ) -> dict | None:
        """GET /sobjects/Opportunity/<id>?fields=... — busca por Salesforce Id.

        Diferente de find_opportunity_by_correlation, este usa o endpoint
        direto de SObject (mais rápido que SOQL, ideal para enriquecimento
        síncrono). Retorna None se 404.
        """
        path = f"/sobjects/Opportunity/{opportunity_id}"
        if fields:
            path += "?fields=" + ",".join(fields)
        try:
            return self.client.get(path)
        except LookupError:  # 404 mapeado pelo _handle_error
            return None

    def upsert_opportunity_by_correlation(
        self, correlation_id: str, fields: dict
    ) -> dict:
        """Upsert nativo via External ID Correlation_Id__c.

        Remove a chave do payload (SF a recebe no path) e envia o restante.
        Retorna {id, created, success}.
        """
        payload = {k: v for k, v in fields.items() if k != "Correlation_Id__c"}
        return self.client.upsert_by_external(
            "Opportunity", "Correlation_Id__c", correlation_id, payload
        )

    def update_opportunity(self, opp_id: str, **fields) -> None:
        self.client.patch(f"/sobjects/Opportunity/{opp_id}", fields)
