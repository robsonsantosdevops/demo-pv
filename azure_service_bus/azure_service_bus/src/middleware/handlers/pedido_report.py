"""Handler para mensagens tipo=pedido_report na fila `relatorios`.

Fluxo:
  1. Valida payload (obrigatórios: opportunity_id, relatorio_sap_id).
  2. Marca Relatorio_SAP__c.Status__c='Em_Processamento' (feedback imediato).
  3. Busca Order no SAP via NumAtCard eq <opportunity_id> (+ DocumentLines).
  4. Não encontrada → marca Status='Erro' com mensagem. ACK.
  5. Encontrada → PATCH Relatorio_SAP__c com todos os campos (DocEntry,
     DocNum, DocTotal, DocDate, DocDueDate, CardCode, DocStatus,
     NumAtCard, Comments, UDFs) + Status='Recebido' +
     Data_Recebimento__c=now, substitui as linhas. ACK.
  6. Erros transientes (5xx, network, 401 persistente) → RETRY.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import requests

from middleware.handlers.base import HandleResult, Handler, HandlerContext
from middleware.integrations.salesforce.service import SalesforceService
from middleware.integrations.sap.client import SapClient
from middleware.integrations.sap.session import SapSessionError

log = logging.getLogger("middleware.handler.pedido_report")

UDF_FIELDS = (
    "U_SF_OppId",
    "U_SF_OppName",
    "U_SF_CorrelationId",
    "U_Pedido_Id",
    "U_Aluno_Nome",
    "U_Aluno_Email",
    "U_Curso_Nome",
    "U_Curso_Descricao",
)

# Mapeia o DocumentStatus do SAP B1 (bost_*) pros valores do picklist
# restrito Relatorio_SAP__c.DocStatus__c no SF (Open/Closed/Cancelled).
_SAP_STATUS_MAP = {
    "bost_Open": "Open",
    "bost_Close": "Closed",
    "bost_Paid": "Closed",
    "bost_Delivered": "Closed",
    "bost_Cancelled": "Cancelled",
    "bost_Canceled": "Cancelled",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _order_to_relatorio_fields(order: dict) -> dict:
    raw_status = order.get("DocumentStatus")
    fields = {
        "DocEntry__c": order.get("DocEntry"),
        "DocNum__c": order.get("DocNum"),
        "DocDate__c": order.get("DocDate"),
        "DocDueDate__c": order.get("DocDueDate"),
        "DocTotal__c": order.get("DocTotal"),
        # Picklist restrito no SF — mapeia bost_* pros valores aceitos.
        # Status desconhecido cai em None (campo não é tocado).
        "DocStatus__c": _SAP_STATUS_MAP.get(raw_status) if raw_status else None,
        "CardCode__c": order.get("CardCode"),
        "NumAtCard__c": order.get("NumAtCard"),
        "Comments__c": order.get("Comments"),
    }
    # Copia UDFs (SAP U_Foo → SF U_Foo__c)
    for udf in UDF_FIELDS:
        fields[f"{udf}__c"] = order.get(udf)
    return fields


def _lines_from_order(order: dict) -> list[dict]:
    out: list[dict] = []
    for ln in order.get("DocumentLines") or []:
        out.append({
            "Line_Number__c": ln.get("LineNum"),
            "ItemCode__c": ln.get("ItemCode"),
            "Quantity__c": ln.get("Quantity"),
            "UnitPrice__c": ln.get("UnitPrice"),
            "Total__c": ln.get("LineTotal"),
        })
    return out


class PedidoReportHandler(Handler):
    name = "pedido_report"

    def __init__(self, sap: SapClient, sf: SalesforceService) -> None:
        self.sap = sap
        self.sf = sf

    def handle(self, payload: dict, ctx: HandlerContext) -> HandleResult:
        opportunity_id = payload.get("opportunity_id")
        relatorio_id = payload.get("relatorio_sap_id")

        missing: list[str] = []
        if not opportunity_id:
            missing.append("opportunity_id")
        if not relatorio_id:
            missing.append("relatorio_sap_id")
        if missing:
            return HandleResult.dlq(f"missing_required: {', '.join(missing)}")

        # 1. Sinaliza "Em_Processamento" pra feedback no SF. Falhas aqui são
        #    transientes (SF); retry resolve.
        try:
            self.sf.update_relatorio_sap(relatorio_id, Status__c="Em_Processamento")
        except requests.HTTPError as e:
            return HandleResult.retry(f"sf_mark_processing_failed:{e}")

        # 2. Busca Order no SAP.
        try:
            order = self.sap.find_order_by_numatcard(opportunity_id)
        except SapSessionError as e:
            return HandleResult.retry(f"sap_session_unavailable:{e}")
        except requests.HTTPError as e:
            status = e.response.status_code if e.response is not None else 0
            body = (e.response.text if e.response is not None else "")[:200]
            if status in (401, 408, 429) or status >= 500:
                return HandleResult.retry(f"sap_http_{status}:{body}")
            if '"-2014"' in body or "(-2014)" in body:
                return HandleResult.retry(f"sap_schema_stale:{body[:100]}")
            # 4xx normal → dado ruim; marca Erro e ACK
            self._mark_erro(relatorio_id, f"SAP HTTP {status}: {body}")
            return HandleResult.ok()
        except requests.RequestException as e:
            return HandleResult.retry(f"sap_network:{e}")

        # 3. Order não encontrada → marca Erro e segue.
        if not order:
            self._mark_erro(
                relatorio_id,
                f"Order não encontrada no SAP para opportunity_id={opportunity_id}",
            )
            log.info(
                "relatorio: order não encontrada — marcado Erro",
                extra={
                    "handler": self.name,
                    "status": "ok",
                    "correlation_id": ctx.correlation_id,
                    "reason": f"relatorio_sap_id={relatorio_id} opp={opportunity_id}",
                },
            )
            return HandleResult.ok()

        # 4. Order encontrada → popula tudo.
        fields = _order_to_relatorio_fields(order)
        fields["Status__c"] = "Recebido"
        fields["Mensagem_Erro__c"] = None  # limpa se tinha erro anterior
        fields["Data_Recebimento__c"] = _now_iso()

        try:
            self.sf.update_relatorio_sap(relatorio_id, **fields)
            linhas = _lines_from_order(order)
            self.sf.replace_relatorio_sap_linhas(relatorio_id, linhas)
        except requests.HTTPError as e:
            status = e.response.status_code if e.response is not None else 0
            if status >= 500 or status == 401:
                return HandleResult.retry(f"sf_http_{status}:{e}")
            # 4xx validação → marca Erro e ACK
            self._mark_erro(relatorio_id, f"SF HTTP {status}: {str(e)[:400]}")
            return HandleResult.ok()

        log.info(
            "relatorio recebido",
            extra={
                "handler": self.name,
                "status": "ok",
                "correlation_id": ctx.correlation_id,
                "reason": f"relatorio={relatorio_id} DocEntry={order.get('DocEntry')} linhas={len(linhas)}",
            },
        )
        return HandleResult.ok()

    def _mark_erro(self, relatorio_id: str, mensagem: str) -> None:
        try:
            self.sf.mark_relatorio_erro(relatorio_id, mensagem)
        except Exception:  # noqa: BLE001
            log.exception("falha ao marcar Erro no Relatorio_SAP__c")
