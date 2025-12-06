"""Configuration unifiee de l'application."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Parametres globaux de l'application."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="allow",
    )

    # Serveur HTTP
    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: list[str] = ["*"]
    cookie_samesite: str = "lax"
    cookie_secure: bool = False
    csrf_max_age_seconds: int = 3600
    health_requires_auth: bool = False

    # Limites et securite
    rate_limit_rps: int = 10
    allowlist_domains: list[str] = []
    allowlist_ports: list[int] = [80, 443]
    jwt_secret: str = "CHANGE_ME"
    reset_admin_flag: str = "app/data/reset_admin.flag"

    # Base de donnees
    db_path: str = "app/data/history.db"

    # Logs et historiques
    log_rotate_mb: int = 5
    log_retention_days: int = 7
    history_retention_days: int = 30
    history_max_mb: int = 200
    mask_secrets_patterns: str = "api_key,token,authorization,password"
    chat_history_max_messages: int = 10
    chat_system_prompt: str = "Tu es IVY, assistant local."
    qa_similarity_threshold: float = 0.9

    # Jeedom
    jeedom_base_url: str | None = None
    jeedom_api_key: str | None = None
    jeedom_verify_ssl: bool = True
    jeedom_timeout: float = 10.0
    jeedom_allowed_hosts: list[str] = []

    # Recherche web
    duckduckgo_max_results: int = 5
    duckduckgo_region: str = "fr-fr"
    duckduckgo_safe_search: str = "moderate"

    # Embeddings
    embedding_model_name: str | None = None

    # Configuration LLM
    llm_provider: str = "llama_cpp"
    llm_model_path: str | None = None
    llm_context_tokens: int = 8192
    llm_max_input_tokens: int = 8000
    llm_max_output_tokens: int = 1024
    llm_temperature: float = 0.7
    llm_n_gpu_layers: int = 0
    llm_speculative_enabled: bool = False
    llm_speculative_model_path: str | None = None
    llm_speculative_context_tokens: int = 4096
    llm_speculative_max_draft_tokens: int = 64
    llm_speculative_n_gpu_layers: int = 0

    # ASR / Voice
    voice_asr_model_path: str | None = None
    voice_asr_device: str = "cpu"
    voice_asr_compute_type: str = "int8"
    voice_tts_voice: str = "fr-FR-piper-high/fr/fr_FR/upmc/medium"
    voice_tts_length_scale: float = 0.92
    voice_tts_pitch: float = 0.85

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

    # Plugins
    plugin_timeout_sec: int = 30
    plugin_max_ram_mb: int = 512
    plugin_sandbox_enabled: bool = True
    plugin_hard_kill_grace_sec: int = 2
    plugin_sandbox_nosandbox: list[str] = ["tasks", "llm", "system_info"]

    # WebSocket
    ws_heartbeat_sec: int = 15
    ws_auth_required: bool = False

    # Scheduler
    scheduler_tz: str = "Europe/Paris"

    # Rate limiting backend
    redis_url: str | None = None
    rate_limit_backend: str = "memory"

    # Observabilite
    enable_metrics: bool = False

    # TensorRT-LLM (optionnel)
    tensorrt_llm_base_url: str | None = None
    tensorrt_llm_chat_endpoint: str = "/v1/chat/completions"
    tensorrt_llm_api_key: str | None = None
    tensorrt_llm_model: str | None = None
    tensorrt_llm_extra_headers: dict[str, str] = {}

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
        """Charge config.json a la racine si present."""
        config_path = Path(__file__).resolve().parents[2] / "config.json"
        if config_path.is_file():
            try:
                return json.loads(config_path.read_text())
            except ValueError:
                return {}
        return {}


@lru_cache()
def get_settings() -> Settings:
    """Retourne une instance de Settings mise en cache."""
    return Settings()
