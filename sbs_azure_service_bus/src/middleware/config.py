"""Carrega e valida configuração via env + .env."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

VALID_QUEUES = ("pedidos", "oportunidades", "contatos", "relatorios")


@dataclass(frozen=True)
class Config:
    service_bus_connection_string: str
    queue_name: str
    log_level: str
    health_port: int
    max_wait_time: int
    max_message_count: int

    @property
    def is_pedidos(self) -> bool:
        return self.queue_name == "pedidos"

    @property
    def is_oportunidades(self) -> bool:
        return self.queue_name == "oportunidades"


class ConfigError(RuntimeError):
    pass


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ConfigError(f"Variável de ambiente obrigatória ausente: {name}")
    return value


def load_config(dotenv_path: Path | None = None) -> Config:
    load_dotenv(dotenv_path=dotenv_path, override=False)

    queue = _require("QUEUE_NAME").strip()
    if queue not in VALID_QUEUES:
        raise ConfigError(
            f"QUEUE_NAME={queue!r} inválido. Valores aceitos: {VALID_QUEUES}"
        )

    return Config(
        service_bus_connection_string=_require("AZURE_SERVICE_BUS_CONNECTION_STRING"),
        queue_name=queue,
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        health_port=int(os.getenv("HEALTH_PORT", "8080")),
        max_wait_time=int(os.getenv("SB_MAX_WAIT_TIME", "5")),
        max_message_count=int(os.getenv("SB_MAX_MESSAGE_COUNT", "10")),
    )
