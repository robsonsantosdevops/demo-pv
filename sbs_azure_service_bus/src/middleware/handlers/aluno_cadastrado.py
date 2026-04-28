"""Handler para mensagens tipo=aluno_cadastrado na fila `contatos`.

Contrato do payload (checkout):
  - Campos obrigatórios: `aluno_id`, `nome_completo`, `email`.
  - Opcionais: `cpf`, `telefone`, `correlation_id`, `created_at`.
  - Se `correlation_id` não vier, derivamos `cadastro-<aluno_id>-<messageId>`
    para ainda conseguir rastrear a jornada nos logs.
  - `telefone` como string vazia (`""`) é tratado como ausente.

Fluxo:
  1. Valida campos obrigatórios (DLQ se faltar).
  2. Garante Account master.
  3. Upsert Contact via External ID Aluno_Id__c (cria novo ou atualiza;
     "promove" Contacts mínimos criados pelo fallback do pedido_criado
     que casam por email mas ainda não têm Aluno_Id__c).
"""

from __future__ import annotations

import logging

from middleware.handlers.base import HandleResult, Handler, HandlerContext
from middleware.integrations.salesforce.service import SalesforceService

log = logging.getLogger("middleware.handler.aluno_cadastrado")


class AlunoCadastradoHandler(Handler):
    name = "aluno_cadastrado"

    def __init__(self, sf: SalesforceService) -> None:
        self.sf = sf

    def handle(self, payload: dict, ctx: HandlerContext) -> HandleResult:
        aluno_id_raw = payload.get("aluno_id")
        nome_completo = payload.get("nome_completo")
        email = payload.get("email")

        missing: list[str] = []
        if aluno_id_raw is None:
            missing.append("aluno_id")
        if not nome_completo:
            missing.append("nome_completo")
        if not email:
            missing.append("email")
        if missing:
            return HandleResult.dlq(f"missing_required: {', '.join(missing)}")

        try:
            aluno_id = int(aluno_id_raw)
        except (TypeError, ValueError):
            return HandleResult.dlq(f"invalid_aluno_id:{aluno_id_raw!r}")

        # correlation_id é opcional — deriva se não vier
        correlation_id = payload.get("correlation_id") or (
            f"cadastro-{aluno_id}-{ctx.message_id or 'unk'}"
        )

        # Sanitiza opcionais: string vazia conta como ausente
        cpf = payload.get("cpf") or None
        telefone = payload.get("telefone") or None

        account_id = self.sf.ensure_account_master()
        contact_id = self.sf.upsert_contact_by_aluno_id(
            account_id=account_id,
            aluno_id=aluno_id,
            full_name=nome_completo,
            email=email,
            cpf=cpf,
            telefone=telefone,
        )
        log.info(
            "contact upsert",
            extra={
                "handler": self.name,
                "status": "ok",
                "correlation_id": correlation_id,
                "reason": f"{contact_id} aluno_id={aluno_id}",
            },
        )
        return HandleResult.ok()
