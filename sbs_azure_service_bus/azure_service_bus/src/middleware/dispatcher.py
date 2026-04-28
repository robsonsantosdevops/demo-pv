"""Roteamento (fila, tipo) → handler.

Os handlers concretos são injetados pelo __main__ conforme a QUEUE_NAME do
processo. Tipo fora do mapa vira DLQ no consumer (reason=unknown_type).
"""

from __future__ import annotations

from middleware.handlers.base import Handler

# Tipos aceitos em cada fila. Usado só como guarda informativa; a verdade
# de runtime está no dict de handlers passado ao Dispatcher.
KNOWN_TYPES: dict[str, set[str]] = {
    # pedido_report / relatorio_sap_request: tipos sinônimos (o Apex evoluiu
    # do primeiro pro segundo). Ambos produzem o mesmo resultado.
    # São aceitos também em "pedidos" como trânsito — CMDT Azure_SB_Config.Pedidos
    # ainda é usado pelo Apex; o Forwarder reencaminha pra `relatorios`.
    "pedidos": {"pedido_criado", "pagamento_aprovado", "pedido_report", "relatorio_sap_request"},
    "oportunidades": {"oportunidade_ganha"},
    "contatos": {"aluno_cadastrado"},
    "relatorios": {"pedido_report", "relatorio_sap_request"},
}


class Dispatcher:
    def __init__(self, handlers: dict[tuple[str, str], Handler]) -> None:
        self._handlers = handlers

    def resolve(self, queue: str, tipo: str) -> Handler | None:
        return self._handlers.get((queue, tipo))
