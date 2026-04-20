from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class LiteratureResult(BaseModel):
    title: str | None = None
    abstract: str | None = None
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    published_date: str | None = None
    doi: str | None = None
    pmid: str | None = None
    source: str
    source_id: str | None = None
    landing_url: str | None = None
    pdf_url: str | None = None
    journal: str | None = None
    publisher: str | None = None
    citation_count: int | None = None
    is_open_access: bool | None = None
    open_access_url: str | None = None
    license: str | None = None
    score: float | None = None
    extras: dict[str, Any] = Field(default_factory=dict)


class ProviderCoverage(BaseModel):
    provider: str
    status: Literal["ok", "skipped", "error"]
    result_count: int = 0
    message: str | None = None
    elapsed_ms: int | None = None


class SearchResponse(BaseModel):
    query: str
    mode: str
    requested_source: str | None = None
    sort: Literal["relevance", "recent"]
    generated_at: str
    result_count: int
    provider_coverage: list[ProviderCoverage]
    warnings: list[str] = Field(default_factory=list)
    results: list[LiteratureResult]


class OpenAccessResponse(BaseModel):
    status: Literal["ok", "error"]
    doi: str
    source: str = "Unpaywall"
    is_open_access: bool | None = None
    best_url: str | None = None
    pdf_url: str | None = None
    license: str | None = None
    oa_status: str | None = None
    journal_is_in_doaj: bool | None = None
    message: str | None = None
    extras: dict[str, Any] = Field(default_factory=dict)


class ProviderStatus(BaseModel):
    provider: str
    category: Literal["search", "resolver"]
    enabled: bool
    ready: bool
    required_credentials: list[str] = Field(default_factory=list)
    missing_credentials: list[str] = Field(default_factory=list)
    message: str | None = None


class HealthCheckResponse(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    generated_at: str
    project_root: str
    app_home: str | None = None
    env_file: str
    env_file_exists: bool
    cache_db_path: str
    codex_config_path: str
    codex_configured: bool
    install_state_path: str | None = None
    install_profile: str | None = None
    runtime_python: str | None = None
    local_model_env_ready: bool | None = None
    local_model_profile: str | None = None
    available_tools: list[str]
    provider_statuses: list[ProviderStatus]
    suggestions: list[str] = Field(default_factory=list)


class DownloadRecord(BaseModel):
    rank: int | None = None
    title: str | None = None
    doi: str | None = None
    source: str | None = None
    landing_url: str | None = None
    selected_url: str | None = None
    attempted_urls: list[str] = Field(default_factory=list)
    local_pdf_path: str | None = None
    local_metadata_path: str | None = None
    status: Literal["downloaded", "skipped", "error"]
    message: str | None = None


class DownloadBatchResponse(BaseModel):
    status: Literal["ok", "partial", "error"]
    generated_at: str
    target_dir: str
    source_kind: str
    source_ref: str
    requested_count: int
    processed_count: int
    downloaded_count: int
    records: list[DownloadRecord]
    warnings: list[str] = Field(default_factory=list)


class OrganizeLibraryResponse(BaseModel):
    status: Literal["ok", "partial", "error"]
    generated_at: str
    target_dir: str
    library_id: str | None = None
    source_kind: str
    source_ref: str
    requested_count: int
    processed_count: int
    downloaded_count: int
    manifest_path: str
    csv_path: str
    markdown_path: str
    bibtex_path: str
    download_checklist_csv_path: str
    download_checklist_markdown_path: str
    records: list[DownloadRecord]
    warnings: list[str] = Field(default_factory=list)


class LibrarySummary(BaseModel):
    id: str
    name: str
    slug: str
    source_kind: str
    source_ref: str
    root_path: str
    archived: bool = False
    tags: list[str] = Field(default_factory=list)
    item_count: int = 0
    active_item_count: int = 0
    favorite_count: int = 0
    created_at: str
    updated_at: str


class LibraryItemEntry(BaseModel):
    id: str
    library_id: str
    rank: int
    title: str
    title_alias: str | None = None
    effective_title: str
    authors: list[str] = Field(default_factory=list)
    source: str
    year: int | None = None
    doi: str | None = None
    landing_url: str | None = None
    pdf_url: str | None = None
    open_access_url: str | None = None
    local_pdf_path: str | None = None
    download_status: str | None = None
    category: str | None = None
    notes: str | None = None
    favorite: bool = False
    archived: bool = False
    tags: list[str] = Field(default_factory=list)
    metadata_path: str | None = None


class ContextBundleSummary(BaseModel):
    id: str
    library_id: str
    name: str
    mode: Literal["compact", "medium"]
    max_items: int
    item_count: int
    preview: str
    resource_uri: str
    created_at: str
    updated_at: str


class LibrariesResponse(BaseModel):
    status: Literal["ok", "error"]
    generated_at: str
    libraries: list[LibrarySummary]


class LibraryDetailResponse(BaseModel):
    status: Literal["ok", "error"]
    generated_at: str
    library: LibrarySummary | None = None
    items: list[LibraryItemEntry] = Field(default_factory=list)
    bundles: list[ContextBundleSummary] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ContextBundleResponse(BaseModel):
    status: Literal["ok", "error"]
    generated_at: str
    bundle: ContextBundleSummary | None = None
    text: str | None = None
    item_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    message: str | None = None


class LibraryMutationResponse(BaseModel):
    status: Literal["ok", "error"]
    generated_at: str
    message: str
    library: LibrarySummary | None = None
    item: LibraryItemEntry | None = None
    bundle: ContextBundleSummary | None = None


class ManagementBootstrapResponse(BaseModel):
    status: Literal["ok", "error"]
    generated_at: str
    libraries: list[LibrarySummary] = Field(default_factory=list)
    selected_library: LibraryDetailResponse | None = None
    selected_bundle: ContextBundleResponse | None = None
    analysis_settings: AnalysisSettingsResponse | None = None
    analysis_reports: list["AnalysisReportSummary"] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class AnalysisSettingsResponse(BaseModel):
    status: Literal["ok", "error"]
    generated_at: str
    analysis_mode: Literal["rules", "hybrid", "semantic_heavy"]
    compute_backend: Literal["auto", "local", "openai"]
    chunk_size: int
    chunk_overlap: int
    max_summary_depth: Literal["shallow", "standard", "deep"]
    forum_enrichment_enabled: bool
    forum_source_profile: Literal["high_trust", "extended", "experimental"]
    forum_sources: list[str] = Field(default_factory=list)
    openai_embedding_model: str
    openai_summary_model: str
    local_embedding_model: str
    local_embedding_dimension: int
    local_embedding_env: str
    local_reranker_model: str
    local_reranker_env: str
    openai_ready: bool
    message: str | None = None


class IngestItemStatus(BaseModel):
    item_id: str
    title: str
    extraction_status: Literal["ready", "skipped", "error"]
    extraction_path: str | None = None
    text_length: int = 0
    chunk_count: int = 0
    discussion_count: int = 0
    message: str | None = None


class IngestResponse(BaseModel):
    status: Literal["ok", "partial", "error"]
    generated_at: str
    library_id: str | None = None
    item_id: str | None = None
    mode: str
    compute_backend: str
    processed_count: int = 0
    ready_count: int = 0
    records: list[IngestItemStatus] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class EvidenceRecord(BaseModel):
    id: str
    item_id: str
    source_type: Literal["pdf", "html", "openreview", "github", "reddit", "huggingface"]
    title: str | None = None
    url: str | None = None
    excerpt: str | None = None
    relevance_score: float | None = None
    confidence_score: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AnalysisSummaryResponse(BaseModel):
    status: Literal["ok", "error"]
    generated_at: str
    library_id: str | None = None
    item_id: str | None = None
    topic: str | None = None
    analysis_mode: str
    compute_backend: str
    title: str
    summary: str
    report_id: str | None = None
    report_path: str | None = None
    key_points: list[str] = Field(default_factory=list)
    evidence: list[EvidenceRecord] = Field(default_factory=list)
    structured_payload: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class AnalysisReportSummary(BaseModel):
    id: str
    library_id: str | None = None
    item_id: str | None = None
    analysis_kind: Literal[
        "library_summary",
        "item_summary",
        "item_compare",
        "topic_analysis",
        "evidence_search",
        "method_card",
        "limitation_card",
        "topic_digest",
        "comparison_matrix",
        "reading_order",
        "research_synthesis",
        "claim_evidence_graph",
        "calibration_protocol_digest",
    ]
    topic: str | None = None
    title: str
    analysis_mode: str
    compute_backend: str
    report_path: str
    created_at: str
    updated_at: str


class AnalysisReportsResponse(BaseModel):
    status: Literal["ok", "error"]
    generated_at: str
    reports: list[AnalysisReportSummary] = Field(default_factory=list)


class AnalysisReportDetailResponse(BaseModel):
    status: Literal["ok", "error"]
    generated_at: str
    report: AnalysisReportSummary | None = None
    summary: str | None = None
    key_points: list[str] = Field(default_factory=list)
    evidence: list[EvidenceRecord] = Field(default_factory=list)
    structured_payload: dict[str, Any] = Field(default_factory=dict)
    message: str | None = None


class DomainProfilesResponse(BaseModel):
    status: Literal["ok", "error"]
    generated_at: str
    profiles: list[dict[str, Any]] = Field(default_factory=list)


# Backward-compatible aliases for older CLI/service code paths.
LibraryListResponse = LibrariesResponse
LibraryItemRecord = LibraryItemEntry
MutationResponse = LibraryMutationResponse

ManagementBootstrapResponse.model_rebuild()
