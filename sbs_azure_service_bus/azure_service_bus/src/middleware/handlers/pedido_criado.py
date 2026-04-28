"""Handler para mensagens tipo=pedido_criado na fila `pedidos`.

Fluxo:
  1. Garante Account master ("Checkout Keeggo - Alunos").
  2. Upsert Contact por email do aluno.
  3. Upsert Opportunity via External ID Correlation_Id__c
     (cria se não existe, atualiza se existe — idempotência nativa).

Contrato do payload (checkout):
  - `numero_pedido` é opcional. Se ausente, derivamos de `pedido_id` como
    `PED-{pedido_id}` para o `Opportunity.Name`.
  - Campos de curso (`curso_titulo`, `curso_descricao`) vêm em `itens[0]`
    e alimentam `Curso_Nome__c` e `Curso_Descricao__c` quando presentes.

Campos custom populados no Opportunity quando presentes no payload:
  - Correlation_Id__c, Pedido_Id__c, Aluno_Id__c
  - Aluno_Nome__c, Aluno_Email__c
  - Parcelas__c, Pedido_Created_At__c
  - Status_Checkout__c
  - Itens_Json__c (array serializado)
  - Curso_Nome__c, Curso_Descricao__c (primeiro item)
  - Description (resumo legível)
"""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta

from middleware.handlers.base import HandleResult, Handler, HandlerContext
from middleware.integrations.salesforce.service import SalesforceService

log = logging.getLogger("middleware.handler.pedido_criado")

STAGE_ABERTO = "Prospecting"
CLOSE_DATE_OFFSET_DAYS = 30
ITENS_JSON_MAX = 32768


class PedidoCriadoHandler(Handler):
    name = "pedido_criado"

    def __init__(self, sf: SalesforceService) -> None:
        self.sf = sf

    def handle(self, payload: dict, ctx: HandlerContext) -> HandleResult:
        correlation_id = payload.get("correlation_id")
        aluno_nome = payload.get("aluno_nome")
        aluno_email = payload.get("aluno_email")
        total_raw = payload.get("total")
        numero_pedido = _resolve_numero_pedido(payload)

        missing = _list_missing(
            correlation_id=correlation_id,
            numero_pedido=numero_pedido,
            aluno_nome=aluno_nome,
            aluno_email=aluno_email,
            total_raw=total_raw,
        )
        if missing:
            return HandleResult.dlq(f"missing_required: {', '.join(missing)}")

        try:
            total = float(total_raw)
        except (TypeError, ValueError):
            return HandleResult.dlq(f"invalid_total:{total_raw!r}")

        account_id = self.sf.ensure_account_master()

        # Match de Contact: primário por Aluno_Id__c (alimentado pelo handler
        # aluno_cadastrado); fallback por email (Contact mínimo criado aqui se
        # a ordem de eventos veio invertida).
        contact_id = _resolve_contact_id(
            sf=self.sf,
            account_id=account_id,
            aluno_id=payload.get("aluno_id"),
            aluno_nome=aluno_nome,
            aluno_email=aluno_email,
        )

        close_date = (date.today() + timedelta(days=CLOSE_DATE_OFFSET_DAYS)).isoformat()
        fields = _opp_fields(
            payload=payload,
            ctx=ctx,
            numero_pedido=numero_pedido,
            account_id=account_id,
            total=total,
            stage=STAGE_ABERTO,
            close_date=close_date,
        )

        result = self.sf.upsert_opportunity_by_correlation(correlation_id, fields)
        opp_id = result.get("id")
        action = "criada" if result.get("created") else "atualizada"

        # Liga Opp ↔ Contact via OpportunityContactRole (Role="Aluno").
        # Idempotente — se já existir, só retorna o Id do role existente.
        if opp_id and contact_id:
            self.sf.ensure_opportunity_contact_role(opp_id, contact_id, role="Aluno")

        log.info(
            f"opportunity {action}",
            extra={
                "handler": self.name,
                "status": "ok",
                "correlation_id": correlation_id,
                "reason": f"{opp_id or '<updated>'} numero_pedido={numero_pedido} contact={contact_id}",
            },
        )
        return HandleResult.ok()


def _resolve_contact_id(
    sf, account_id: str, aluno_id, aluno_nome: str, aluno_email: str
) -> str | None:
    """Acha Contact por Aluno_Id__c (primário) ou cria/atualiza por email
    (fallback)."""
    if aluno_id is not None:
        try:
            existing = sf.find_contact_by_aluno_id(int(aluno_id))
        except (TypeError, ValueError):
            existing = None
        if existing:
            return existing["Id"]
    # Fallback: cria Contact mínimo por email (ou atualiza se já existir).
    return sf.upsert_contact_by_email(account_id, aluno_nome, aluno_email)


def _resolve_numero_pedido(payload: dict) -> str | None:
    """Usa `numero_pedido` se o checkout enviar; senão deriva de `pedido_id`."""
    nome = payload.get("numero_pedido")
    if nome:
        return nome
    pedido_id = payload.get("pedido_id")
    if pedido_id is None:
        return None
    return f"PED-{pedido_id}"


def _list_missing(
    *,
    correlation_id: object,
    numero_pedido: object,
    aluno_nome: object,
    aluno_email: object,
    total_raw: object,
) -> list[str]:
    missing: list[str] = []
    if not correlation_id:
        missing.append("correlation_id")
    if not numero_pedido:
        missing.append("numero_pedido|pedido_id")
    if not aluno_nome:
        missing.append("aluno_nome")
    if not aluno_email:
        missing.append("aluno_email")
    if total_raw is None:
        missing.append("total")
    return missing


def _opp_fields(
    payload: dict,
    ctx: HandlerContext,
    numero_pedido: str,
    account_id: str,
    total: float,
    stage: str,
    close_date: str,
) -> dict:
    itens_json = json.dumps(payload.get("itens") or [], ensure_ascii=False)
    if len(itens_json) > ITENS_JSON_MAX:
        itens_json = itens_json[: ITENS_JSON_MAX - 1] + "]"

    primeiro_item = _first_item(payload)

    fields = {
        "Name": numero_pedido,
        "AccountId": account_id,
        "StageName": stage,
        "CloseDate": close_date,
        "Amount": total,
        "Description": _build_description(payload, ctx),
        # Custom — pedido
        "Correlation_Id__c": payload["correlation_id"],
        "Pedido_Id__c": payload.get("pedido_id"),
        "Aluno_Id__c": payload.get("aluno_id"),
        "Aluno_Nome__c": payload.get("aluno_nome"),
        "Aluno_Email__c": payload.get("aluno_email"),
        "Parcelas__c": payload.get("parcelas"),
        "Pedido_Created_At__c": payload.get("created_at"),
        "Status_Checkout__c": payload.get("status"),
        "Itens_Json__c": itens_json,
        # Custom — curso (primeiro item do array)
        "Curso_Nome__c": primeiro_item.get("curso_titulo"),
        "Curso_Descricao__c": primeiro_item.get("curso_descricao"),
    }
    # Remove chaves cujo valor é None — evita SF errors e mantém o payload enxuto.
    return {k: v for k, v in fields.items() if v is not None}


def _first_item(payload: dict) -> dict:
    itens = payload.get("itens") or []
    if itens and isinstance(itens[0], dict):
        return itens[0]
    return {}


def _build_description(payload: dict, ctx: HandlerContext) -> str:
    itens = payload.get("itens") or []
    itens_desc = "; ".join(
        f"{it.get('curso_titulo') or it.get('curso_id')}"
        f" x{it.get('quantidade')}"
        + (f" @ {it.get('preco_unitario')}" if it.get("preco_unitario") is not None else "")
        for it in itens
        if isinstance(it, dict)
    )
    lines = [
        f"correlation_id: {ctx.correlation_id}",
        f"pedido_id: {payload.get('pedido_id')}",
        f"parcelas: {payload.get('parcelas')}",
        f"status_checkout: {payload.get('status')}",
        f"created_at: {payload.get('created_at')}",
    ]
    if itens_desc:
        lines.append(f"itens: {itens_desc}")
    return "\n".join(lines)
