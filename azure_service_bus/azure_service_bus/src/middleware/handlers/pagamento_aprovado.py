"""Handler para mensagens tipo=pagamento_aprovado na fila `pedidos`.

Contrato do payload (checkout):
  - `numero_pedido` é opcional. Se presente, usado no fallback de busca.
    Se ausente mas `pedido_id` vier, deriva `PED-{pedido_id}`.
  - Campos obrigatórios: `correlation_id` e `valor`.

Fluxo:
  1. Busca Opportunity por Correlation_Id__c (chave canônica).
     Fallback: busca por Name usando numero_pedido (explícito ou derivado
     de pedido_id) — serve para Opps legadas sem Correlation_Id__c.
  2. Se não encontrada → retry (ordem invertida com pedido_criado).
  3. Se encontrada e já Closed Won → no-op idempotente.
  4. Caso geral → StageName=Closed Won, Amount=valor, CloseDate=hoje,
     campos de pagamento preenchidos, Description com merge.
"""

from __future__ import annotations

import logging
from datetime import date

from middleware.handlers.base import HandleResult, Handler, HandlerContext
from middleware.integrations.salesforce.service import SalesforceService

log = logging.getLogger("middleware.handler.pagamento_aprovado")

STAGE_GANHA = "Closed Won"


class PagamentoAprovadoHandler(Handler):
    name = "pagamento_aprovado"

    def __init__(self, sf: SalesforceService) -> None:
        self.sf = sf

    def handle(self, payload: dict, ctx: HandlerContext) -> HandleResult:
        valor_raw = payload.get("valor")
        correlation_id = payload.get("correlation_id")

        missing: list[str] = []
        if not correlation_id:
            missing.append("correlation_id")
        if valor_raw is None:
            missing.append("valor")
        if missing:
            return HandleResult.dlq(f"missing_required: {', '.join(missing)}")

        try:
            valor = float(valor_raw)
        except (TypeError, ValueError):
            return HandleResult.dlq(f"invalid_valor:{valor_raw!r}")

        numero_pedido_fallback = _numero_pedido_for_fallback(payload)

        opp = self.sf.find_opportunity_by_correlation(correlation_id)
        if not opp and numero_pedido_fallback:
            opp = self.sf.find_opportunity_by_name(numero_pedido_fallback)
        if not opp:
            return HandleResult.retry(
                f"opp_not_found:{correlation_id}/{numero_pedido_fallback}"
            )

        if opp.get("StageName") == STAGE_GANHA:
            log.info(
                "opportunity já estava Closed Won",
                extra={
                    "handler": self.name,
                    "status": "ok",
                    "correlation_id": correlation_id,
                    "reason": opp["Id"],
                },
            )
            return HandleResult.ok()

        merged_description = _merge_description(opp.get("Description") or "", payload, ctx)
        fields = {
            "StageName": STAGE_GANHA,
            "Amount": valor,
            "CloseDate": date.today().isoformat(),
            "Description": merged_description,
            # Custom — pagamento
            "Pagamento_Id__c": payload.get("pagamento_id"),
            "Pagamento_Protocolo__c": payload.get("protocolo"),
            "Forma_Pagamento__c": payload.get("forma_pagamento"),
            "Status_Pagamento__c": payload.get("status_pagamento"),
            "Status_Pedido__c": payload.get("status_pedido"),
            "Cartao_Final__c": payload.get("cartao_final"),
        }
        # Remove None pra não escrever null em campo que o pagamento não trouxe.
        fields = {k: v for k, v in fields.items() if v is not None}

        self.sf.update_opportunity(opp["Id"], **fields)
        log.info(
            "opportunity fechada",
            extra={
                "handler": self.name,
                "status": "ok",
                "correlation_id": correlation_id,
                "reason": f"{opp['Id']} forma={payload.get('forma_pagamento')}",
            },
        )
        return HandleResult.ok()


def _numero_pedido_for_fallback(payload: dict) -> str | None:
    """Usado só pra fallback SOQL em Opps legadas. Não obrigatório."""
    nome = payload.get("numero_pedido")
    if nome:
        return nome
    pedido_id = payload.get("pedido_id")
    if pedido_id is None:
        return None
    return f"PED-{pedido_id}"


def _merge_description(current: str, payload: dict, ctx: HandlerContext) -> str:
    add = [
        "",
        "--- pagamento_aprovado ---",
        f"correlation_id: {ctx.correlation_id}",
        f"pagamento_id: {payload.get('pagamento_id')}",
        f"protocolo: {payload.get('protocolo')}",
        f"forma_pagamento: {payload.get('forma_pagamento')}",
        f"parcelas: {payload.get('parcelas')}",
        f"status_pedido: {payload.get('status_pedido')}",
        f"created_at: {payload.get('created_at')}",
    ]
    return (current.rstrip() + "\n" + "\n".join(add)).strip()
