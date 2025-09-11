"""Configuration unifiée de l'application."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Parametres de l'application (serveur, logs, DB)."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Réseau / serveur
    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: list[str] = ["*"]

    # Limites et sécurité
    rate_limit_rps: int = 10
    allowlist_domains: list[str] = []
    allowlist_ports: list[int] = [80, 443]
    jwt_secret: str = "CHANGE_ME"
    reset_admin_flag: str = "app/data/reset_admin.flag"

    # Base de données
    db_path: str = "app/data/history.db"

    # Logs
    log_rotate_mb: int = 5
    log_retention_days: int = 7

    # RAG
    rag_inbox_dir: str = "app/data/inbox"
    rag_knowledge_dir: str = "app/data/knowledge"
    rag_index_dir: str = "app/data/faiss_index"
    rag_enable_ocr: bool = True
    rag_ocr_lang: str = "fra"
    rag_chunk_size: int = 1000
    rag_chunk_overlap: int = 200
    rag_reindex_interval_minutes: int = 60
    rag_watchers_enabled: bool = True
    rag_reindex_enabled: bool = True
    rag_max_file_mb: int = 50
    rag_index_timeout_sec: int = 120

    # Historique / logs
    history_retention_days: int = 30
    history_max_mb: int = 200
    mask_secrets_patterns: str = "api_key,token,authorization,password"

    # Plugins (ressources)
    plugin_timeout_sec: int = 30
    plugin_max_ram_mb: int = 512

    # WebSocket
    ws_heartbeat_sec: int = 15
    ws_auth_required: bool = False
    ws_auth_required: bool = False

    # LLM limites
    llm_max_input_tokens: int = 8000
    llm_max_output_tokens: int = 1024

    # Scheduler
    scheduler_tz: str = "Europe/Paris"

    # Rate limit backend
    redis_url: str | None = None
    rate_limit_backend: str = "memory"  # memory|redis

    # Plugins sandbox
    plugin_sandbox_enabled: bool = True
    plugin_hard_kill_grace_sec: int = 2
    plugin_sandbox_nosandbox: list[str] = ["tasks", "llm", "system_info"]

    # Observabilité
    enable_metrics: bool = False

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            cls.json_config_settings_source,
            file_secret_settings,
        )

    @staticmethod
    def json_config_settings_source() -> dict[str, object]:
        """Charge depuis ``config.json`` à la racine si présent."""
        config_path = Path(__file__).resolve().parents[2] / "config.json"
        if config_path.is_file():
            try:
                return json.loads(config_path.read_text())
            except ValueError:
                return {}
        return {}


@lru_cache()
def get_settings() -> Settings:
    """Retourne une instance de :class:`Settings` mise en cache."""
    return Settings()
