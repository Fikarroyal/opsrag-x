"""Environment-based configuration (no hard-coded secrets, no absolute paths)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _find_data_dir() -> Path:
    """Locate the repository `data/` directory by walking up from this file."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "data" / "raw").is_dir():
            return parent / "data"
    return here.parents[1] / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore", protected_namespaces=())

    app_env: str = "development"
    app_name: str = "OpsRAG-X"
    log_level: str = "INFO"
    cors_origins: str = "*"

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/opsragx"
    data_dir: Path = Field(default_factory=_find_data_dir)
    demo_mode: bool = True
    frontend_dist: Path | None = None  # built SPA to serve from the backend (set automatically if frontend/dist exists)
    auto_bootstrap: bool = False

    # Authentication (cookie session + bearer token). Set AUTH_REQUIRED=false only for isolated tests.
    auth_required: bool = True
    secret_key: str | None = None  # SECRET_KEY; if unset a random key is generated once and stored in <data_dir>/.secret_key
    session_ttl_hours: int = 168
    cookie_secure: bool = False  # set COOKIE_SECURE=true when served over HTTPS

    # LLM (optional at runtime - the app degrades to DEMO_FALLBACK_MODE)
    llm_provider: str = "ollama"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"
    llm_model: str | None = None
    llm_timeout_seconds: float = 45.0
    llm_enabled: bool = True

    # Embeddings
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_backend: str = "auto"  # auto | sentence-transformers | hashing
    embedding_dim: int = 384

    # MCP
    mcp_server_url: str = "http://localhost:8001"
    mcp_transport: str = "mcp"  # mcp (streamable-http protocol) | rest (facade, used in tests)
    mcp_timeout_seconds: float = 12.0

    # Retrieval
    top_k: int = 8
    semantic_weight: float = 0.45
    temporal_weight: float = 0.25
    category_weight: float = 0.10
    service_weight: float = 0.10
    source_weight: float = 0.10
    history_half_life_days: float = 30.0
    sop_half_life_days: float = 180.0

    # Investigation / evidence
    correlation_window_minutes: int = 15
    log_half_life_minutes: float = 10.0
    tool_snapshot_offset_minutes: int = 5  # demo: tools are queried "as of" incident time + offset
    hyp_evidence_weight: float = 0.35
    hyp_temporal_weight: float = 0.20
    hyp_topology_weight: float = 0.15
    hyp_history_weight: float = 0.10
    hyp_state_weight: float = 0.10
    hyp_source_weight: float = 0.10
    min_confidence_for_root_cause: float = 0.40

    @property
    def active_llm_model(self) -> str:
        return self.llm_model or self.ollama_model

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def retrieval_weights(self) -> dict[str, float]:
        w = {
            "semantic": self.semantic_weight,
            "temporal": self.temporal_weight,
            "category": self.category_weight,
            "service": self.service_weight,
            "source": self.source_weight,
        }
        total = sum(w.values()) or 1.0
        return {k: v / total for k, v in w.items()}

    @property
    def hypothesis_weights(self) -> dict[str, float]:
        w = {
            "evidence": self.hyp_evidence_weight,
            "temporal": self.hyp_temporal_weight,
            "topology": self.hyp_topology_weight,
            "history": self.hyp_history_weight,
            "state": self.hyp_state_weight,
            "source": self.hyp_source_weight,
        }
        total = sum(w.values()) or 1.0
        return {k: v / total for k, v in w.items()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
