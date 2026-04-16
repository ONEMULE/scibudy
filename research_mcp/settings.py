from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from research_mcp.paths import APP_HOME, ENV_FILE


def _default_cache_path() -> Path:
    return APP_HOME / "state" / "research.db"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", env_file=str(ENV_FILE), env_file_encoding="utf-8")

    user_agent: str = Field(
        default="codex-research-mcp/0.1",
        validation_alias=AliasChoices("RESEARCH_MCP_USER_AGENT"),
    )
    request_timeout_sec: float = Field(
        default=20.0,
        validation_alias=AliasChoices("RESEARCH_MCP_REQUEST_TIMEOUT_SEC"),
    )
    max_retries: int = Field(
        default=2,
        validation_alias=AliasChoices("RESEARCH_MCP_MAX_RETRIES"),
    )
    backoff_base_sec: float = Field(
        default=1.0,
        validation_alias=AliasChoices("RESEARCH_MCP_BACKOFF_BASE_SEC"),
    )
    max_results_per_provider: int = Field(
        default=25,
        validation_alias=AliasChoices("RESEARCH_MCP_MAX_RESULTS_PER_PROVIDER"),
    )
    provider_timeout_sec: float = Field(
        default=45.0,
        validation_alias=AliasChoices("RESEARCH_MCP_PROVIDER_TIMEOUT_SEC"),
    )
    search_total_timeout_sec: float = Field(
        default=110.0,
        validation_alias=AliasChoices("RESEARCH_MCP_SEARCH_TOTAL_TIMEOUT_SEC"),
    )
    max_provider_workers: int = Field(
        default=6,
        validation_alias=AliasChoices("RESEARCH_MCP_MAX_PROVIDER_WORKERS"),
    )
    cache_db_path: Path = Field(
        default_factory=_default_cache_path,
        validation_alias=AliasChoices("RESEARCH_MCP_CACHE_DB_PATH"),
    )
    log_level: str = Field(
        default="ERROR",
        validation_alias=AliasChoices("RESEARCH_MCP_LOG_LEVEL"),
    )
    analysis_mode: str = Field(
        default="hybrid",
        validation_alias=AliasChoices("RESEARCH_MCP_ANALYSIS_MODE"),
    )
    compute_backend: str = Field(
        default="auto",
        validation_alias=AliasChoices("RESEARCH_MCP_COMPUTE_BACKEND"),
    )
    chunk_size: int = Field(
        default=1800,
        validation_alias=AliasChoices("RESEARCH_MCP_CHUNK_SIZE"),
    )
    chunk_overlap: int = Field(
        default=250,
        validation_alias=AliasChoices("RESEARCH_MCP_CHUNK_OVERLAP"),
    )
    max_summary_depth: str = Field(
        default="standard",
        validation_alias=AliasChoices("RESEARCH_MCP_MAX_SUMMARY_DEPTH"),
    )
    forum_enrichment_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("RESEARCH_MCP_FORUM_ENRICHMENT_ENABLED"),
    )
    forum_source_profile: str = Field(
        default="high_trust",
        validation_alias=AliasChoices("RESEARCH_MCP_FORUM_SOURCE_PROFILE"),
    )
    forum_sources: str = Field(
        default="openreview,github",
        validation_alias=AliasChoices("RESEARCH_MCP_FORUM_SOURCES"),
    )
    openai_embedding_model: str = Field(
        default="text-embedding-3-small",
        validation_alias=AliasChoices("RESEARCH_MCP_OPENAI_EMBEDDING_MODEL"),
    )
    openai_summary_model: str = Field(
        default="gpt-5.4-mini",
        validation_alias=AliasChoices("RESEARCH_MCP_OPENAI_SUMMARY_MODEL"),
    )
    local_embedding_model: str = Field(
        default="Qwen/Qwen3-Embedding-4B",
        validation_alias=AliasChoices("RESEARCH_MCP_LOCAL_EMBEDDING_MODEL"),
    )
    local_embedding_dimension: int = Field(
        default=2560,
        validation_alias=AliasChoices("RESEARCH_MCP_LOCAL_EMBEDDING_DIMENSION"),
    )
    local_embedding_env: str = Field(
        default="research_embed",
        validation_alias=AliasChoices("RESEARCH_MCP_LOCAL_EMBEDDING_ENV"),
    )
    local_reranker_model: str = Field(
        default="Qwen/Qwen3-Reranker-4B",
        validation_alias=AliasChoices("RESEARCH_MCP_LOCAL_RERANKER_MODEL"),
    )
    local_reranker_env: str = Field(
        default="research_embed",
        validation_alias=AliasChoices("RESEARCH_MCP_LOCAL_RERANKER_ENV"),
    )

    enable_openalex: bool = Field(default=True, validation_alias=AliasChoices("RESEARCH_MCP_ENABLE_OPENALEX"))
    enable_arxiv: bool = Field(default=True, validation_alias=AliasChoices("RESEARCH_MCP_ENABLE_ARXIV"))
    enable_crossref: bool = Field(default=True, validation_alias=AliasChoices("RESEARCH_MCP_ENABLE_CROSSREF"))
    enable_semantic_scholar: bool = Field(
        default=True,
        validation_alias=AliasChoices("RESEARCH_MCP_ENABLE_SEMANTIC_SCHOLAR"),
    )
    allow_public_semantic_scholar: bool = Field(
        default=True,
        validation_alias=AliasChoices("RESEARCH_MCP_ALLOW_PUBLIC_SEMANTIC_SCHOLAR"),
    )
    enable_pubmed: bool = Field(default=True, validation_alias=AliasChoices("RESEARCH_MCP_ENABLE_PUBMED"))
    enable_europepmc: bool = Field(default=True, validation_alias=AliasChoices("RESEARCH_MCP_ENABLE_EUROPEPMC"))
    enable_doaj: bool = Field(default=True, validation_alias=AliasChoices("RESEARCH_MCP_ENABLE_DOAJ"))
    enable_core: bool = Field(default=True, validation_alias=AliasChoices("RESEARCH_MCP_ENABLE_CORE"))

    openalex_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("OPENALEX_API_KEY", "RESEARCH_MCP_OPENALEX_API_KEY"),
    )
    crossref_mailto: str | None = Field(
        default=None,
        validation_alias=AliasChoices("CROSSREF_MAILTO", "RESEARCH_MCP_CROSSREF_MAILTO"),
    )
    semantic_scholar_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("SEMANTIC_SCHOLAR_API_KEY", "RESEARCH_MCP_SEMANTIC_SCHOLAR_API_KEY"),
    )
    ncbi_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("NCBI_API_KEY", "RESEARCH_MCP_NCBI_API_KEY"),
    )
    unpaywall_email: str | None = Field(
        default=None,
        validation_alias=AliasChoices("UNPAYWALL_EMAIL", "RESEARCH_MCP_UNPAYWALL_EMAIL"),
    )
    core_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("CORE_API_KEY", "RESEARCH_MCP_CORE_API_KEY"),
    )
    openai_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("OPENAI_API_KEY", "RESEARCH_MCP_OPENAI_API_KEY"),
    )

    @model_validator(mode="after")
    def _prepare(self) -> "Settings":
        self.cache_db_path = self.cache_db_path.expanduser()
        self.cache_db_path.parent.mkdir(parents=True, exist_ok=True)
        self.analysis_mode = self.analysis_mode.strip().lower()
        self.compute_backend = self.compute_backend.strip().lower()
        self.max_summary_depth = self.max_summary_depth.strip().lower()
        self.forum_source_profile = self.forum_source_profile.strip().lower()
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
