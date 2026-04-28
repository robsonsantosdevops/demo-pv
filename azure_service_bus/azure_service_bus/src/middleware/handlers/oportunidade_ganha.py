"""Handler para mensagens tipo=oportunidade_ganha na fila `oportunidades`.

Produzida pelo trigger Apex `OpportunityGanhaTrigger` quando uma Opp vira
StageName=Closed Won. Payload conforme o Apex compartilhado:

    {
      "correlation_id": "sf-<OppId>",
      "opportunity_id": "<OppId>",
      "name": "<Opp.Name>",
      "amount": <valor>,
      "close_date": "YYYY-MM-DD",
      "account_id": "<SF AccountId>",
      "owner_id": "<SF UserId>"
    }

Fluxo:
  1. Idempotência via NumAtCard == opportunity_id — se já existe, skip.
  2. Se `sf_service` estiver disponível, busca a Opp no SF para enriquecer
     a Order com Curso_Nome__c, Curso_Descricao__c, Aluno_Nome__c, etc.
     Fail-soft: se SF falhar, segue com dados mínimos do payload.
  3. POST /Orders com NumAtCard, Comments resumo + UDFs estruturados.

Mapeamento para SAP B1 Order (demo):
  - DocDate / DocDueDate: today / today + 30.
  - CardCode: default configurado em SAP_DEFAULT_CARDCODE.
  - DocumentLines: 1 linha com ItemCode default, Quantity=1.0, UnitPrice=amount.
  - NumAtCard: opportunity_id (idempotência).
  - Comments: resumo legível (≤254 chars).
  - UDFs: U_SF_OppId, U_SF_OppName, U_SF_CorrelationId, U_Pedido_Id,
          U_Aluno_Nome, U_Aluno_Email, U_Curso_Nome, U_Curso_Descricao.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

import requests

from middleware.handlers.base import HandleResult, Handler, HandlerContext
from middleware.integrations.sap.client import SapClient
from middleware.integrations.sap.session import SapSessionError

log = logging.getLogger("middleware.handler.oportunidade_ganha")

DUE_DAYS = 30
COMMENTS_MAX = 254

SF_ENRICHMENT_FIELDS = [
    "Name",
    "Amount",
    "Correlation_Id__c",
    "Pedido_Id__c",
    "Aluno_Nome__c",
    "Aluno_Email__c",
    "Curso_Nome__c",
    "Curso_Descricao__c",
]


def _find_existing_order(sap: SapClient, opportunity_id: str) -> dict | None:
    """Consulta idempotente: existe Order com NumAtCard == opportunity_id?

    Usamos NumAtCard (customer reference do SAP B1, varchar 100, nativamente
    filtrável com `eq`) em vez de Comments, porque Comments é memo field e
    SAP B1 Service Layer não suporta `contains` nele.

    Retorna o primeiro match ou None. Se o filter falhar, devolve None
    (não-bloqueante — melhor duplicata que falha total).
    """
    escaped = opportunity_id.replace("'", "''")
    url = (
        f"{sap.config.base_url}/Orders"
        f"?$filter=NumAtCard eq '{escaped}'"
        f"&$select=DocEntry,DocNum,NumAtCard"
        f"&$top=1"
    )
    try:
        resp = sap.get(url)
    except requests.HTTPError as e:
        status = e.response.status_code if e.response is not None else 0
        log.warning(
            "idempotency check falhou, seguindo sem verificar",
            extra={"status": "warn", "reason": f"sap_http_{status}"},
        )
        return None
    except requests.RequestException as e:
        log.warning(
            "idempotency check falhou (network), seguindo sem verificar",
            extra={"status": "warn", "reason": f"sap_network:{e}"},
        )
        return None

    values = resp.get("value") or []
    return values[0] if values else None


def _fetch_sf_enrichment(sf_service, opp_id: str) -> dict:
    """Busca campos adicionais da Opp no Salesforce. Fail-soft: em erro
    retorna {} para o handler seguir com dados do payload."""
    if sf_service is None:
        return {}
    try:
        opp = sf_service.get_opportunity_by_id(opp_id, fields=SF_ENRICHMENT_FIELDS)
    except Exception as e:  # noqa: BLE001
        log.warning(
            "enriquecimento SF falhou, seguindo sem extras",
            extra={"status": "warn", "reason": f"sf_err:{type(e).__name__}:{str(e)[:80]}"},
        )
        return {}
    return opp or {}


class OportunidadeGanhaHandler(Handler):
    name = "oportunidade_ganha"

    def __init__(self, sap: SapClient, sf_service=None) -> None:
        self.sap = sap
        self.sf_service = sf_service

    def handle(self, payload: dict, ctx: HandlerContext) -> HandleResult:
        opp_id = payload.get("opportunity_id")
        opp_name = payload.get("name")
        amount_raw = payload.get("amount")

        if not opp_id or not opp_name or amount_raw is None:
            return HandleResult.dlq("missing_required: opportunity_id/name/amount")

        try:
            amount = float(amount_raw)
        except (TypeError, ValueError):
            return HandleResult.dlq(f"invalid_amount:{amount_raw!r}")

        existing = _find_existing_order(self.sap, opp_id)
        if existing:
            log.info(
                "order já existia para esta opp — skip",
                extra={
                    "handler": self.name,
                    "status": "ok",
                    "correlation_id": ctx.correlation_id,
                    "reason": f"DocEntry={existing.get('DocEntry')} DocNum={existing.get('DocNum')} opp={opp_id}",
                },
            )
            return HandleResult.ok()

        # Enriquecimento opcional — pega dados da Opp no SF se possível.
        extras = _fetch_sf_enrichment(self.sf_service, opp_id)

        today = date.today()
        order_payload = _build_order_payload(
            payload=payload,
            ctx=ctx,
            extras=extras,
            amount=amount,
            sap_config=self.sap.config,
            today=today,
        )

        try:
            result = self.sap.create_order(order_payload)
        except SapSessionError as e:
            return HandleResult.retry(f"sap_session_unavailable:{e}")
        except requests.HTTPError as e:
            status = e.response.status_code if e.response is not None else 0
            body = (e.response.text if e.response is not None else "")[:300]
            # SAP code -2014 ("Internal error") normalmente é schema cache stale
            # (session autenticada antes de UDFs novos). É transiente — resolve
            # com session nova, mesmo sendo 400.
            if '"-2014"' in body or "(-2014)" in body:
                return HandleResult.retry(f"sap_schema_stale:{body[:100]}")
            if 400 <= status < 500 and status not in (401, 408, 429):
                return HandleResult.dlq(f"sap_http_{status}:{body}")
            return HandleResult.retry(f"sap_http_{status}:{body}")
        except requests.RequestException as e:
            return HandleResult.retry(f"sap_network:{e}")

        doc_entry = result.get("DocEntry")
        doc_num = result.get("DocNum")
        log.info(
            "order criada no SAP",
            extra={
                "handler": self.name,
                "status": "ok",
                "correlation_id": ctx.correlation_id,
                "reason": f"DocEntry={doc_entry} DocNum={doc_num} opp={opp_id}",
            },
        )
        return HandleResult.ok()


def _build_order_payload(
    payload: dict, ctx: HandlerContext, extras: dict, amount: float,
    sap_config, today: date,
) -> dict:
    opp_id = payload["opportunity_id"]
    opp_name = extras.get("Name") or payload.get("name")
    curso_nome = extras.get("Curso_Nome__c")
    curso_descricao = extras.get("Curso_Descricao__c")
    aluno_nome = extras.get("Aluno_Nome__c")
    aluno_email = extras.get("Aluno_Email__c")
    correlation_id = extras.get("Correlation_Id__c") or ctx.correlation_id
    pedido_id_raw = extras.get("Pedido_Id__c")
    # SF devolve Number como float (ex.: 42.0) — convertemos pra int quando faz sentido.
    pedido_id: int | None = None
    if pedido_id_raw is not None:
        try:
            pedido_id = int(pedido_id_raw)
        except (TypeError, ValueError):
            pedido_id = None

    order: dict = {
        "DocDate": today.isoformat() + "T00:00:00Z",
        "DocDueDate": (today + timedelta(days=DUE_DAYS)).isoformat() + "T00:00:00Z",
        "CardCode": sap_config.default_cardcode,
        "BPL_IDAssignedToInvoice": sap_config.default_bpl_id,
        "NumAtCard": opp_id,
        "Comments": _build_comments(
            opp_id=opp_id, opp_name=opp_name, curso_nome=curso_nome,
            aluno_nome=aluno_nome, aluno_email=aluno_email,
            pedido_id=pedido_id, correlation_id=correlation_id,
        ),
        "DocumentLines": [
            {
                "ItemCode": sap_config.default_item_code,
                "Quantity": 1.0,
                "UnitPrice": amount,
            }
        ],
        # UDFs estruturados
        "U_SF_OppId": opp_id,
        "U_SF_OppName": opp_name,
        "U_SF_CorrelationId": correlation_id,
        "U_Pedido_Id": pedido_id,
        "U_Aluno_Nome": aluno_nome,
        "U_Aluno_Email": aluno_email,
        "U_Curso_Nome": curso_nome,
        "U_Curso_Descricao": curso_descricao,
    }
    # Remove UDFs None — evita ruído no payload enviado ao SAP.
    return {k: v for k, v in order.items() if v is not None}


def _build_comments(
    opp_id: str, opp_name, curso_nome, aluno_nome, aluno_email,
    pedido_id, correlation_id,
) -> str:
    """Gera o Comments resumido, respeitando o limite de 254 chars do SAP."""
    parts = [f"Opp: {opp_name} ({opp_id})"]
    if curso_nome:
        parts.append(f"Curso: {curso_nome}")
    if aluno_nome:
        aluno = aluno_nome
        if aluno_email:
            aluno += f" <{aluno_email}>"
        parts.append(f"Aluno: {aluno}")
    if pedido_id is not None:
        parts.append(f"Pedido: {pedido_id}")
    if correlation_id:
        parts.append(f"CorrId: {correlation_id}")
    full = " | ".join(parts)
    if len(full) > COMMENTS_MAX:
        full = full[: COMMENTS_MAX - 1] + "…"
    return full
