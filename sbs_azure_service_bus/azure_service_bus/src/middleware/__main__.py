"""Entrypoint: python -m middleware."""

from __future__ import annotations

import logging
import signal
import sys
import threading
from pathlib import Path

from middleware.config import Config, ConfigError, load_config
from middleware.consumer import Consumer
from middleware.dispatcher import Dispatcher
from middleware.handlers.aluno_cadastrado import AlunoCadastradoHandler
from middleware.handlers.base import Handler
from middleware.handlers.forwarder import ForwarderHandler
from middleware.handlers.oportunidade_ganha import OportunidadeGanhaHandler
from middleware.handlers.pagamento_aprovado import PagamentoAprovadoHandler
from middleware.handlers.pedido_criado import PedidoCriadoHandler
from middleware.handlers.pedido_report import PedidoReportHandler
from middleware.health import HealthState, start_health_server
from middleware.integrations.salesforce import (
    SalesforceClient,
    SalesforceService,
    load_salesforce_config,
)
from middleware.integrations.sap import SapClient, SapSession, load_sap_config
from middleware.logging_setup import setup_logging


def _build_handlers(config: Config, log: logging.Logger) -> dict[tuple[str, str], Handler]:
    """Monta o stack específico da fila que este processo está consumindo.

    Falha alta se as dependências (SF/SAP) não estiverem configuradas — melhor
    crashar no boot do que descobrir no meio do loop.
    """
    if config.queue_name == "pedidos":
        sf_config = load_salesforce_config()
        log.info(
            "salesforce: usando host de login OAuth/SOAP",
            extra={"status": "boot", "reason": sf_config.login_base},
        )
        sf_client = SalesforceClient(sf_config)
        sf_client.authenticate()
        log.info(
            "salesforce conectado",
            extra={"status": "ok", "reason": sf_client.instance_url},
        )
        sf = SalesforceService(sf_client)
        # pedido_report chega aqui apenas como trânsito (Apex usa CMDT
        # Azure_SB_Config.Pedidos). Reencaminha pra fila `relatorios`.
        forwarder = ForwarderHandler(
            sb_connection_string=config.service_bus_connection_string,
            target_queue="relatorios",
        )
        return {
            ("pedidos", "pedido_criado"): PedidoCriadoHandler(sf),
            ("pedidos", "pagamento_aprovado"): PagamentoAprovadoHandler(sf),
            # Ambos os sinônimos do Apex: redireciona pra fila relatorios
            ("pedidos", "pedido_report"): forwarder,
            ("pedidos", "relatorio_sap_request"): forwarder,
        }

    if config.queue_name == "contatos":
        sf_config = load_salesforce_config()
        log.info(
            "salesforce: usando host de login OAuth/SOAP",
            extra={"status": "boot", "reason": sf_config.login_base},
        )
        sf_client = SalesforceClient(sf_config)
        sf_client.authenticate()
        log.info(
            "salesforce conectado",
            extra={"status": "ok", "reason": sf_client.instance_url},
        )
        sf = SalesforceService(sf_client)
        return {
            ("contatos", "aluno_cadastrado"): AlunoCadastradoHandler(sf),
        }

    if config.queue_name == "oportunidades":
        sap_config = load_sap_config()
        sap_session = SapSession()
        sap_client = SapClient(sap_config, sap_session)
        log.info(
            "sap client configurado",
            extra={"status": "ok", "reason": sap_config.base_url},
        )
        # SF é opcional no pod de oportunidades — usado só para enriquecer
        # a Order com Curso/Aluno antes de postar no SAP. Falha aqui é
        # tolerada (fail-soft): o handler segue sem enrichment.
        sf_service = None
        try:
            sf_config = load_salesforce_config()
            log.info(
                "salesforce: usando host de login OAuth/SOAP (enrichment)",
                extra={"status": "boot", "reason": sf_config.login_base},
            )
            sf_client = SalesforceClient(sf_config)
            sf_client.authenticate()
            sf_service = SalesforceService(sf_client)
            log.info(
                "salesforce conectado (enrichment)",
                extra={"status": "ok", "reason": sf_client.instance_url},
            )
        except Exception as e:  # noqa: BLE001
            log.warning(
                "salesforce indisponível — orders sairão sem enrichment",
                extra={"status": "warn", "reason": f"{type(e).__name__}:{str(e)[:120]}"},
            )
        return {
            ("oportunidades", "oportunidade_ganha"): OportunidadeGanhaHandler(
                sap_client, sf_service=sf_service
            ),
        }

    if config.queue_name == "relatorios":
        # Precisa de SAP (pra ler Order) + SF (pra atualizar Relatorio_SAP__c).
        sap_config = load_sap_config()
        sap_session = SapSession()
        sap_client = SapClient(sap_config, sap_session)
        sf_config = load_salesforce_config()
        log.info(
            "salesforce: usando host de login OAuth/SOAP",
            extra={"status": "boot", "reason": sf_config.login_base},
        )
        sf_client = SalesforceClient(sf_config)
        sf_client.authenticate()
        sf = SalesforceService(sf_client)
        log.info(
            "relatorios handler pronto (SAP+SF)",
            extra={"status": "ok", "reason": sf_client.instance_url},
        )
        handler = PedidoReportHandler(sap_client, sf)
        return {
            ("relatorios", "pedido_report"): handler,
            ("relatorios", "relatorio_sap_request"): handler,
        }

    return {}


def main() -> int:
    try:
        config = load_config()
    except ConfigError as e:
        print(f"[config] {e}", file=sys.stderr)
        return 2

    log_dir = Path(__file__).resolve().parents[2] / "logs"
    log = setup_logging(level=config.log_level, log_dir=log_dir)
    log.info("middleware iniciando", extra={"queue": config.queue_name, "status": "boot"})

    try:
        handlers = _build_handlers(config, log)
    except Exception as e:  # noqa: BLE001
        # Inclui tipo + mensagem no próprio `msg` (JSON) — várias UIs truncam o campo `exc`.
        log.error(
            "falha montando handlers — abortando boot — %s: %s",
            type(e).__name__,
            e,
            extra={
                "status": "boot_failed",
                "queue": config.queue_name,
                "reason": f"{type(e).__name__}: {e!s}"[:4000],
            },
            exc_info=True,
        )
        return 3

    health = HealthState()
    server = start_health_server(config.health_port, health)

    shutdown = threading.Event()

    def _handle_signal(signum: int, _frame: object) -> None:
        log.warning(
            "sinal recebido, iniciando shutdown",
            extra={"status": "shutting_down", "reason": signal.Signals(signum).name},
        )
        shutdown.set()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    consumer = Consumer(
        config=config,
        dispatcher=Dispatcher(handlers),
        health=health,
        shutdown=shutdown,
    )

    exit_code = 0
    try:
        consumer.run()
    except Exception:  # noqa: BLE001
        logging.getLogger("middleware").exception("erro fatal no consumer")
        exit_code = 1
    finally:
        server.shutdown()
        log.info("middleware encerrado", extra={"status": "stopped"})

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
