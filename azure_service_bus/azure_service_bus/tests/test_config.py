"""Testes de middleware.config.load_config."""

from __future__ import annotations

import pytest

from middleware.config import ConfigError, load_config


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Garante que os testes não sejam afetados por env vars reais ou .env na raiz."""
    for key in (
        "QUEUE_NAME",
        "AZURE_SERVICE_BUS_CONNECTION_STRING",
        "LOG_LEVEL",
        "HEALTH_PORT",
        "SB_MAX_WAIT_TIME",
        "SB_MAX_MESSAGE_COUNT",
    ):
        monkeypatch.delenv(key, raising=False)


def test_load_config_raises_without_queue_name(monkeypatch, tmp_path):
    monkeypatch.setenv("AZURE_SERVICE_BUS_CONNECTION_STRING", "Endpoint=sb://x")
    with pytest.raises(ConfigError, match="QUEUE_NAME"):
        load_config(dotenv_path=tmp_path / "nonexistent")


def test_load_config_raises_without_connection_string(monkeypatch, tmp_path):
    monkeypatch.setenv("QUEUE_NAME", "pedidos")
    with pytest.raises(ConfigError, match="AZURE_SERVICE_BUS_CONNECTION_STRING"):
        load_config(dotenv_path=tmp_path / "nonexistent")


def test_load_config_rejects_unknown_queue(monkeypatch, tmp_path):
    monkeypatch.setenv("AZURE_SERVICE_BUS_CONNECTION_STRING", "Endpoint=sb://x")
    monkeypatch.setenv("QUEUE_NAME", "random-queue")
    with pytest.raises(ConfigError, match="inválido"):
        load_config(dotenv_path=tmp_path / "nonexistent")


def test_load_config_minimal_success(monkeypatch, tmp_path):
    monkeypatch.setenv("AZURE_SERVICE_BUS_CONNECTION_STRING", "Endpoint=sb://x")
    monkeypatch.setenv("QUEUE_NAME", "pedidos")
    cfg = load_config(dotenv_path=tmp_path / "nonexistent")
    assert cfg.queue_name == "pedidos"
    assert cfg.is_pedidos is True
    assert cfg.is_oportunidades is False
    assert cfg.log_level == "INFO"
    assert cfg.health_port == 8080
    assert cfg.max_wait_time == 5
    assert cfg.max_message_count == 10


def test_load_config_oportunidades_flags(monkeypatch, tmp_path):
    monkeypatch.setenv("AZURE_SERVICE_BUS_CONNECTION_STRING", "Endpoint=sb://x")
    monkeypatch.setenv("QUEUE_NAME", "oportunidades")
    cfg = load_config(dotenv_path=tmp_path / "nonexistent")
    assert cfg.is_oportunidades is True
    assert cfg.is_pedidos is False


def test_load_config_contatos_is_accepted(monkeypatch, tmp_path):
    monkeypatch.setenv("AZURE_SERVICE_BUS_CONNECTION_STRING", "Endpoint=sb://x")
    monkeypatch.setenv("QUEUE_NAME", "contatos")
    cfg = load_config(dotenv_path=tmp_path / "nonexistent")
    assert cfg.queue_name == "contatos"
    assert cfg.is_pedidos is False
    assert cfg.is_oportunidades is False


def test_load_config_relatorios_is_accepted(monkeypatch, tmp_path):
    monkeypatch.setenv("AZURE_SERVICE_BUS_CONNECTION_STRING", "Endpoint=sb://x")
    monkeypatch.setenv("QUEUE_NAME", "relatorios")
    cfg = load_config(dotenv_path=tmp_path / "nonexistent")
    assert cfg.queue_name == "relatorios"


def test_load_config_respects_overrides(monkeypatch, tmp_path):
    monkeypatch.setenv("AZURE_SERVICE_BUS_CONNECTION_STRING", "Endpoint=sb://x")
    monkeypatch.setenv("QUEUE_NAME", "pedidos")
    monkeypatch.setenv("LOG_LEVEL", "debug")
    monkeypatch.setenv("HEALTH_PORT", "9090")
    monkeypatch.setenv("SB_MAX_WAIT_TIME", "20")
    monkeypatch.setenv("SB_MAX_MESSAGE_COUNT", "50")

    cfg = load_config(dotenv_path=tmp_path / "nonexistent")
    assert cfg.log_level == "DEBUG"  # uppercased
    assert cfg.health_port == 9090
    assert cfg.max_wait_time == 20
    assert cfg.max_message_count == 50
