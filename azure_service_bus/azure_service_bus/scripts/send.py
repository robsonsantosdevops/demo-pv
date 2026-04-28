"""Publica mensagens de teste nas filas do middleware.

Uso:
    # pedido_criado com numero gerado (fila default: pedidos)
    python scripts/send.py

    # pagamento_aprovado referenciando um pedido anterior
    python scripts/send.py --tipo pagamento_aprovado --numero-pedido PED-TEST-1776893810907

    # Encadear pedido → pagamento com mesmo numero_pedido e correlation_id
    python scripts/send.py --numero-pedido PED-DEMO-1 --correlation-id jornada-demo-1
    python scripts/send.py --tipo pagamento_aprovado \\
        --numero-pedido PED-DEMO-1 --correlation-id jornada-demo-1

    # oportunidade_ganha (fila default muda para oportunidades)
    python scripts/send.py --tipo oportunidade_ganha --opp-id OPP-DEMO-1 --amount 15000

    # Publicar duas vezes a mesma opp (teste de idempotência do handler SAP)
    python scripts/send.py --tipo oportunidade_ganha --opp-id OPP-IDEM-001 --amount 1234
    python scripts/send.py --tipo oportunidade_ganha --opp-id OPP-IDEM-001 --amount 1234

Os payloads seguem o mesmo shape produzido pelos producers reais:
- pedido_criado/pagamento_aprovado: checkout (Node)
- oportunidade_ganha: trigger Apex no Salesforce
"""

import argparse
import json
import os
import random
import string
import uuid
from datetime import datetime, timezone

from azure.servicebus import ServiceBusClient, ServiceBusMessage
from dotenv import load_dotenv

load_dotenv()
CONN_STR = os.getenv("AZURE_SERVICE_BUS_CONNECTION_STRING")

QUEUE_POR_TIPO = {
    "pedido_criado": "pedidos",
    "pagamento_aprovado": "pedidos",
    "oportunidade_ganha": "oportunidades",
    "aluno_cadastrado": "contatos",
    "pedido_report": "relatorios",
}


def enviar_mensagem(payload: dict, tipo: str, queue: str, traceparent: str | None = None) -> str:
    body = {
        "tipo": tipo,
        "payload": payload,
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    sufixo = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    message_id = f"{tipo}-{int(datetime.now().timestamp() * 1000)}-{sufixo}"

    app_props = {"tipo": tipo}
    if traceparent:
        app_props["traceparent"] = traceparent

    mensagem = ServiceBusMessage(
        body=json.dumps(body, ensure_ascii=False),
        content_type="application/json",
        message_id=message_id,
        application_properties=app_props,
    )

    with ServiceBusClient.from_connection_string(CONN_STR) as client:
        with client.get_queue_sender(queue) as sender:
            sender.send_messages(mensagem)

    print(f"[ok] enviado | queue={queue} tipo={tipo} messageId={message_id}")
    ident = payload.get("numero_pedido") or payload.get("opportunity_id")
    print(f"     ident={ident} correlation_id={payload.get('correlation_id')}")
    return message_id


def _payload_pedido_criado(
    numero_pedido: str, correlation_id: str, aluno_email: str,
    aluno_id: int | None = None, aluno_nome: str = "Teste Middleware",
) -> dict:
    return {
        "correlation_id": correlation_id,
        "pedido_id": random.randint(100, 999),
        "numero_pedido": numero_pedido,
        "aluno_id": aluno_id if aluno_id is not None else random.randint(10, 99),
        "aluno_nome": aluno_nome,
        "aluno_email": aluno_email,
        "total": "12990.00",
        "parcelas": 10,
        "status": "aguardando_pagamento",
        "itens": [
            {
                "curso_id": "enem-online",
                "curso_titulo": "Enem Online",
                "quantidade": 1,
                "preco_unitario": 12990,
            }
        ],
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


def _payload_pagamento_aprovado(
    numero_pedido: str, correlation_id: str, aluno_email: str,
    aluno_id: int | None = None, aluno_nome: str = "Teste Middleware",
) -> dict:
    return {
        "correlation_id": correlation_id,
        "pagamento_id": random.randint(10, 99),
        "protocolo": f"PAG-{int(datetime.now().timestamp()*1000)}-{random.randint(100, 999)}",
        "pedido_id": random.randint(100, 999),
        "numero_pedido": numero_pedido,
        "aluno_id": aluno_id if aluno_id is not None else random.randint(10, 99),
        "aluno_nome": aluno_nome,
        "aluno_email": aluno_email,
        "forma_pagamento": "pix",
        "valor": "12990.00",
        "parcelas": 10,
        "status_pagamento": "aprovado",
        "status_pedido": "pago",
        "cartao_final": None,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


def _payload_aluno_cadastrado(
    aluno_id: int, nome_completo: str, email: str,
    cpf: str | None, telefone: str | None, correlation_id: str | None,
) -> dict:
    # correlation_id é opcional no contrato oficial — só inclui se veio
    payload: dict = {
        "aluno_id": aluno_id,
        "nome_completo": nome_completo,
        "email": email,
        "telefone": telefone or "",
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    if cpf:
        payload["cpf"] = cpf
    if correlation_id:
        payload["correlation_id"] = correlation_id
    return payload


def _payload_pedido_report(
    opp_id: str, opp_name: str, relatorio_id: str, correlation_id: str,
) -> dict:
    return {
        "correlation_id": correlation_id,
        "opportunity_id": opp_id,
        "opportunity_name": opp_name,
        "account_id": "001TEST",
        "relatorio_sap_id": relatorio_id,
        "requested_by_user_id": "005TEST",
        "requested_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


def _payload_oportunidade_ganha(opp_id: str, opp_name: str, amount: float, correlation_id: str) -> dict:
    return {
        "correlation_id": correlation_id,
        "opportunity_id": opp_id,
        "name": opp_name,
        "amount": amount,
        "close_date": datetime.now(timezone.utc).date().isoformat(),
        "account_id": "001TESTACC0000001",
        "owner_id": "005TESTOWN0000001",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--tipo",
        choices=["pedido_criado", "pagamento_aprovado", "oportunidade_ganha", "aluno_cadastrado", "pedido_report"],
        default="pedido_criado",
    )
    parser.add_argument("--relatorio-id", default=None, help="Id do Relatorio_SAP__c (pedido_report).")
    parser.add_argument("--queue", default=None, help="Default depende do tipo.")
    parser.add_argument("--numero-pedido", default=None)
    parser.add_argument("--correlation-id", default=None)
    parser.add_argument("--aluno-email", default="teste.middleware@keeggo.com")
    parser.add_argument("--aluno-id", type=int, default=None, help="ID estável do aluno (para aluno_cadastrado / pedido_criado).")
    parser.add_argument("--aluno-nome", default="Teste Middleware", help="Nome do aluno (pedido/pagamento). Para aluno_cadastrado, use --nome-completo.")
    parser.add_argument("--nome-completo", default=None, help="Nome completo do aluno (aluno_cadastrado).")
    parser.add_argument("--email", default=None, help="Email do aluno (aluno_cadastrado). Fallback: --aluno-email.")
    parser.add_argument("--cpf", default=None, help="CPF do aluno (aluno_cadastrado, opcional).")
    parser.add_argument("--telefone", default=None, help="Telefone do aluno (aluno_cadastrado, opcional).")
    # oportunidade_ganha
    parser.add_argument("--opp-id", default=None, help="opportunity_id (Salesforce Opp Id).")
    parser.add_argument("--opp-name", default=None, help="Nome da Opportunity.")
    parser.add_argument("--amount", type=float, default=12990.0, help="Valor da Opp/Order.")
    args = parser.parse_args()

    queue = args.queue or QUEUE_POR_TIPO[args.tipo]
    corr = args.correlation_id

    if args.tipo == "pedido_criado":
        numero = args.numero_pedido or f"PED-TEST-{int(datetime.now().timestamp()*1000)}"
        corr = corr or f"jornada-teste-{uuid.uuid4()}"
        payload = _payload_pedido_criado(numero, corr, args.aluno_email, args.aluno_id, args.aluno_nome)
    elif args.tipo == "pagamento_aprovado":
        numero = args.numero_pedido or f"PED-TEST-{int(datetime.now().timestamp()*1000)}"
        corr = corr or f"jornada-teste-{uuid.uuid4()}"
        payload = _payload_pagamento_aprovado(numero, corr, args.aluno_email, args.aluno_id, args.aluno_nome)
    elif args.tipo == "oportunidade_ganha":
        opp_id = args.opp_id or f"OPP-TEST-{int(datetime.now().timestamp()*1000)}"
        opp_name = args.opp_name or opp_id
        corr = corr or f"sf-{opp_id}"
        payload = _payload_oportunidade_ganha(opp_id, opp_name, args.amount, corr)
    elif args.tipo == "pedido_report":
        opp_id = args.opp_id or f"006TEST{int(datetime.now().timestamp())}"
        opp_name = args.opp_name or "PED-TEST"
        relatorio = args.relatorio_id or f"a01TEST{int(datetime.now().timestamp())}"
        corr = corr or str(uuid.uuid4())
        payload = _payload_pedido_report(opp_id, opp_name, relatorio, corr)
    else:  # aluno_cadastrado
        aluno_id = args.aluno_id if args.aluno_id is not None else random.randint(1000, 9999)
        nome = args.nome_completo or args.aluno_nome
        mail = args.email or args.aluno_email
        # correlation_id opcional — só atribui se usuário passou explicitamente
        payload = _payload_aluno_cadastrado(
            aluno_id=aluno_id, nome_completo=nome, email=mail,
            cpf=args.cpf, telefone=args.telefone, correlation_id=args.correlation_id,
        )

    enviar_mensagem(payload, tipo=args.tipo, queue=queue)


if __name__ == "__main__":
    main()
