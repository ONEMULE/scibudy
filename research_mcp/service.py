from __future__ import annotations

import concurrent.futures
from functools import lru_cache
from pathlib import Path
import time

from research_mcp import __version__
from research_mcp.analysis_config import settings_response
from research_mcp.analysis_engine import AnalysisEngine
from research_mcp.cache import SQLiteStateStore
from research_mcp.catalog import CatalogStore
from research_mcp.client import ResearchHttpClient
from research_mcp.errors import ProviderRequestError, ResearchMCPError
from research_mcp.install_state import load_install_state
from research_mcp.library import LibraryManager, response_to_results
from research_mcp.models import (
    AnalysisSettingsResponse,
    AnalysisReportDetailResponse,
    AnalysisReportsResponse,
    AnalysisSummaryResponse,
    ContextBundleResponse,
    DownloadBatchResponse,
    HealthCheckResponse,
    IngestResponse,
    LibrariesResponse,
    LibraryDetailResponse,
    LibraryMutationResponse,
    ManagementBootstrapResponse,
    OpenAccessResponse,
    OrganizeLibraryResponse,
    ProviderCoverage,
    ProviderStatus,
    SearchResponse,
)
from research_mcp.paths import APP_HOME, CODEX_CONFIG_FILE, ENV_FILE, INSTALL_STATE_FILE, PROJECT_ROOT, command_path
from research_mcp.providers import build_providers
from research_mcp.query_expansion import expand_search_query
from research_mcp.rate_limit import RateLimiter
from research_mcp.ranking import dedupe_and_rank
from research_mcp.settings import Settings, get_settings
from research_mcp.utils import canonical_doi, now_utc_iso


MODE_TO_PROVIDERS = {
    "general": ["openalex", "crossref", "semanticscholar", "doaj", "core"],
    "preprint": ["arxiv", "openalex", "semanticscholar", "core"],
    "biomed": ["pubmed", "europepmc", "openalex", "doaj", "core"],
}


class ResearchService:
    def __init__(
        self,
        settings: Settings | None = None,
        state: SQLiteStateStore | None = None,
        client: ResearchHttpClient | None = None,
        providers=None,
        oa_resolver=None,
    ) -> None:
        self.settings = settings or get_settings()
        self.state = state or SQLiteStateStore(self.settings.cache_db_path)
        self.catalog = CatalogStore(self.settings.cache_db_path)
        self.rate_limiter = RateLimiter(self.state)
        self.client = client or ResearchHttpClient(self.settings, self.state, self.rate_limiter)
        built_providers, built_resolver = build_providers(self.settings, self.client)
        self.providers = providers or built_providers
        self.oa_resolver = oa_resolver or built_resolver
        self.library = LibraryManager(self.settings, oa_resolver=self.oa_resolver)
        self.analysis = AnalysisEngine(self.settings, self.settings.cache_db_path)

    def search_literature(self, query: str, mode: str = "general", limit: int = 10, sort: str = "relevance") -> SearchResponse:
        mode = mode.strip().lower()
        sort = _validate_sort(sort)
        if mode not in MODE_TO_PROVIDERS:
            raise ValueError("mode must be one of: general, preprint, biomed")
        query = _validate_query(query)
        limit = _validate_limit(limit)
        return self._run_provider_group(query=query, provider_names=MODE_TO_PROVIDERS[mode], mode=mode, limit=limit, sort=sort)

    def search_biomed(self, query: str, limit: int = 10, sort: str = "relevance") -> SearchResponse:
        return self.search_literature(query=query, mode="biomed", limit=limit, sort=sort)

    def search_source(self, source: str, query: str, limit: int = 10, sort: str = "relevance") -> SearchResponse:
        source_key = source.strip().lower()
        sort = _validate_sort(sort)
        if source_key not in self.providers:
            raise ValueError("unsupported source")
        query = _validate_query(query)
        limit = _validate_limit(limit)
        response = self._run_provider_group(query=query, provider_names=[source_key], mode="source", limit=limit, sort=sort)
        response.requested_source = source_key
        return response

    def resolve_open_access(self, doi: str) -> OpenAccessResponse:
        normalized = canonical_doi(doi) or doi.strip()
        ready, message = self.oa_resolver.ready()
        if not ready:
            return OpenAccessResponse(status="error", doi=normalized, message=message)
        try:
            return self.oa_resolver.resolve(normalized)
        except ResearchMCPError as exc:
            return OpenAccessResponse(status="error", doi=normalized, message=str(exc))

    def download_pdfs(
        self,
        *,
        run_id: str | None = None,
        csv_path: str | None = None,
        target_dir: str | None = None,
        limit: int = 20,
    ) -> DownloadBatchResponse:
        results, source_kind, source_ref = self.library.load_results(run_id=run_id, csv_path=csv_path)
        return self.library.download_pdfs(
            results=results,
            target_dir=target_dir,
            limit=_validate_limit(limit),
            source_kind=source_kind,
            source_ref=source_ref,
        )

    def organize_library(
        self,
        *,
        run_id: str | None = None,
        csv_path: str | None = None,
        target_dir: str | None = None,
        limit: int = 50,
        download_pdfs: bool = True,
        name: str | None = None,
    ) -> OrganizeLibraryResponse:
        results, source_kind, source_ref = self.library.load_results(run_id=run_id, csv_path=csv_path)
        response = self.library.organize_library(
            results=results,
            target_dir=target_dir,
            limit=_validate_limit(limit),
            source_kind=source_kind,
            source_ref=source_ref,
            download_pdfs=download_pdfs,
        )
        response.library_id = self._register_library(response, results, name=name)
        return response

    def collect_library(
        self,
        *,
        query: str,
        mode: str = "general",
        limit: int = 20,
        sort: str = "relevance",
        target_dir: str | None = None,
        download_pdfs: bool = True,
        name: str | None = None,
    ) -> OrganizeLibraryResponse:
        search_response = self.search_literature(query=query, mode=mode, limit=limit, sort=sort)
        results = response_to_results(search_response)
        response = self.library.organize_library(
            results=results,
            target_dir=target_dir,
            limit=search_response.result_count,
            source_kind="query",
            source_ref=query,
            download_pdfs=download_pdfs,
        )
        response.library_id = self._register_library(response, results, name=name)
        return response

    def import_library(self, path: str, name: str | None = None) -> LibraryMutationResponse:
        manifest_path = Path(path).expanduser().resolve()
        if manifest_path.is_dir():
            manifest_path = manifest_path / "manifest.json"
        if not manifest_path.exists():
            return LibraryMutationResponse(status="error", generated_at=now_utc_iso(), message="manifest not found")
        return self.catalog.import_library_from_manifest(manifest_path, name=name)

    def list_libraries(self, include_archived: bool = False) -> LibrariesResponse:
        return self.catalog.list_libraries(include_archived=include_archived)

    def read_library(self, library_id: str, include_archived_items: bool = False) -> LibraryDetailResponse:
        return self.catalog.read_library(library_id, include_archived_items=include_archived_items)

    def rename_library(self, library_id: str, new_name: str) -> LibraryMutationResponse:
        return self.catalog.rename_library(library_id, new_name)

    def archive_library(self, library_id: str) -> LibraryMutationResponse:
        return self.catalog.archive_library(library_id)

    def restore_library(self, library_id: str) -> LibraryMutationResponse:
        return self.catalog.restore_library(library_id)

    def tag_library(self, library_id: str, tags: list[str]) -> LibraryMutationResponse:
        return self.catalog.tag_library(library_id, tags)

    def update_library_item(
        self,
        item_id: str,
        *,
        title_alias: str | None = None,
        notes: str | None = None,
        favorite: bool | None = None,
        tags: list[str] | None = None,
    ) -> LibraryMutationResponse:
        return self.catalog.update_library_item(item_id, title_alias=title_alias, notes=notes, favorite=favorite, tags=tags)

    def archive_library_item(self, item_id: str) -> LibraryMutationResponse:
        return self.catalog.archive_library_item(item_id)

    def restore_library_item(self, item_id: str) -> LibraryMutationResponse:
        return self.catalog.restore_library_item(item_id)

    def generate_context_bundle(
        self,
        library_id: str,
        *,
        name: str | None = None,
        mode: str = "compact",
        max_items: int = 12,
        favorites_only: bool = False,
    ) -> ContextBundleResponse:
        return self.catalog.generate_context_bundle(library_id, name=name, mode=mode, max_items=max_items, favorites_only=favorites_only)

    def read_context_bundle(self, bundle_id: str) -> ContextBundleResponse:
        return self.catalog.read_context_bundle(bundle_id)

    def get_analysis_settings(self) -> AnalysisSettingsResponse:
        return settings_response(self.settings)

    def update_analysis_settings(self, **updates) -> AnalysisSettingsResponse:
        response = self.analysis.update_settings(**updates)
        self.settings = get_settings()
        return response

    def ingest_library(self, library_id: str, *, include_forums: bool = True, reingest: bool = False) -> IngestResponse:
        return self.analysis.ingest_library(self.read_library(library_id, include_archived_items=False), include_forums=include_forums, reingest=reingest)

    def ingest_library_item(self, item_id: str, *, include_forums: bool = True, reingest: bool = False) -> IngestResponse:
        for library in self.list_libraries(include_archived=True).libraries:
            detail = self.read_library(library.id, include_archived_items=True)
            for item in detail.items:
                if item.id == item_id:
                    record = self.analysis.ingest_item(library.id, item, include_forums=include_forums, reingest=reingest)
                    return IngestResponse(
                        status="ok" if record.extraction_status == "ready" else "error",
                        generated_at=now_utc_iso(),
                        library_id=library.id,
                        item_id=item_id,
                        mode=self.settings.analysis_mode,
                        compute_backend=self.settings.compute_backend,
                        processed_count=1,
                        ready_count=1 if record.extraction_status == "ready" else 0,
                        records=[record],
                    )
        return IngestResponse(status="error", generated_at=now_utc_iso(), item_id=item_id, mode=self.settings.analysis_mode, compute_backend=self.settings.compute_backend, warnings=["item not found"])

    def summarize_library(self, library_id: str, *, topic: str | None = None) -> AnalysisSummaryResponse:
        return self.analysis.summarize_library(self.read_library(library_id), topic=topic)

    def summarize_library_item(self, item_id: str, *, topic: str | None = None) -> AnalysisSummaryResponse:
        for library in self.list_libraries(include_archived=True).libraries:
            detail = self.read_library(library.id, include_archived_items=True)
            for item in detail.items:
                if item.id == item_id:
                    return self.analysis.summarize_item(item, topic=topic)
        return AnalysisSummaryResponse(status="error", generated_at=now_utc_iso(), analysis_mode=self.settings.analysis_mode, compute_backend=self.settings.compute_backend, title="Item summary", summary="Item not found.")

    def compare_library_items(self, item_ids: list[str], *, topic: str | None = None) -> AnalysisSummaryResponse:
        items = []
        for library in self.list_libraries(include_archived=True).libraries:
            detail = self.read_library(library.id, include_archived_items=True)
            items.extend([item for item in detail.items if item.id in item_ids])
        return self.analysis.compare_items(items, topic=topic)

    def analyze_library_topic(self, library_id: str, topic: str) -> AnalysisSummaryResponse:
        return self.analysis.analyze_topic(self.read_library(library_id), topic=topic)

    def search_library_evidence(self, library_id: str, query: str, max_hits: int = 8) -> AnalysisSummaryResponse:
        return self.analysis.search_library_evidence(self.read_library(library_id), query=query, max_hits=max_hits)

    def build_research_synthesis(self, library_id: str, topic: str, max_items: int = 50) -> AnalysisSummaryResponse:
        cleaned_topic = _validate_query(topic)
        return self.analysis.build_research_synthesis(
            self.read_library(library_id),
            topic=cleaned_topic,
            max_items=_validate_limit(max_items),
        )

    def read_synthesis_report(self, report_id: str) -> AnalysisReportDetailResponse:
        return self.read_analysis_report(report_id)

    def list_analysis_reports(self, *, library_id: str | None = None, item_id: str | None = None) -> AnalysisReportsResponse:
        return self.analysis.list_reports(library_id=library_id, item_id=item_id)

    def read_analysis_report(self, report_id: str) -> AnalysisReportDetailResponse:
        return self.analysis.read_report(report_id)

    def get_ui_bootstrap(self, library_id: str | None = None, include_archived: bool = False) -> ManagementBootstrapResponse:
        libraries = self.list_libraries(include_archived=include_archived)
        selected_library = None
        analysis_reports = []
        if library_id:
            selected_library = self.read_library(library_id)
        elif libraries.libraries:
            selected_library = self.read_library(libraries.libraries[0].id)
        if selected_library and selected_library.library:
            analysis_reports = self.list_analysis_reports(library_id=selected_library.library.id).reports[:12]
        return ManagementBootstrapResponse(
            status="ok",
            generated_at=now_utc_iso(),
            libraries=libraries.libraries,
            selected_library=selected_library,
            analysis_settings=self.get_analysis_settings(),
            analysis_reports=analysis_reports,
            warnings=[],
        )

    def render_library_manager(self, *, library_id: str | None = None, include_archived: bool = False) -> dict:
        bootstrap = self.get_ui_bootstrap(library_id=library_id, include_archived=include_archived)
        return {
            "content": [{"type": "text", "text": "Library manager ready."}],
            "structuredContent": {
                "libraryCount": len(bootstrap.libraries),
                "selectedLibraryId": bootstrap.selected_library.library.id if bootstrap.selected_library and bootstrap.selected_library.library else None,
                "analysisMode": self.settings.analysis_mode,
                "computeBackend": self.settings.compute_backend,
            },
            "_meta": {"bootstrap": bootstrap.model_dump(mode="json")},
        }

    def health_check(self) -> HealthCheckResponse:
        provider_statuses: list[ProviderStatus] = []
        degraded = False

        for provider in self.providers.values():
            enabled = True if not provider.enabled_flag else bool(getattr(self.settings, provider.enabled_flag))
            missing = [env_name for env_name, attr_name in provider.required_settings if not getattr(self.settings, attr_name)]
            ready, message = provider.ready()
            if enabled and not ready:
                degraded = True
            provider_statuses.append(
                ProviderStatus(
                    provider=provider.name,
                    category="search",
                    enabled=enabled,
                    ready=ready,
                    required_credentials=[env_name for env_name, _ in provider.required_settings],
                    missing_credentials=missing,
                    message=message,
                )
            )

        missing = [env_name for env_name, attr_name in self.oa_resolver.required_settings if not getattr(self.settings, attr_name)]
        oa_ready, oa_message = self.oa_resolver.ready()
        if not oa_ready:
            degraded = True
        provider_statuses.append(
            ProviderStatus(
                provider=self.oa_resolver.name,
                category="resolver",
                enabled=True,
                ready=oa_ready,
                required_credentials=[env_name for env_name, _ in self.oa_resolver.required_settings],
                missing_credentials=missing,
                message=oa_message,
            )
        )

        suggestions: list[str] = []
        install_state = load_install_state()
        if not ENV_FILE.exists():
            suggestions.append(f"Run '{command_path()} setup --install-codex' to create {ENV_FILE.name} and wire Codex.")
        if not CODEX_CONFIG_FILE.exists() or "[mcp_servers.research]" not in CODEX_CONFIG_FILE.read_text(encoding="utf-8", errors="ignore"):
            suggestions.append(f"Run '{command_path()} install-codex' to register the MCP server in Codex.")
        for status in provider_statuses:
            if status.missing_credentials and not status.ready:
                suggestions.append(f"Add {', '.join(status.missing_credentials)} to {ENV_FILE}.")
        if self.settings.analysis_mode in {"hybrid", "semantic_heavy"} and not self.settings.openai_api_key:
            suggestions.append(
                "OPENAI_API_KEY is not configured; semantic retrieval will use the local heuristic embedding backend."
            )
        local_env_python = Path.home() / "anaconda3" / "envs" / self.settings.local_embedding_env / "bin" / "python"
        if not local_env_python.exists():
            suggestions.append(
                f"Local GPU embedding env is missing. Create {self.settings.local_embedding_env} and install torch/transformers to use {self.settings.local_embedding_model}."
            )
        suggestions.append(
            f"Forum source profile is '{self.settings.forum_source_profile}' with sources {self.settings.forum_sources}."
        )

        return HealthCheckResponse(
            status="degraded" if degraded else "ok",
            version=__version__,
            generated_at=now_utc_iso(),
            project_root=str(PROJECT_ROOT),
            app_home=str(APP_HOME),
            env_file=str(ENV_FILE),
            env_file_exists=ENV_FILE.exists(),
            cache_db_path=str(self.settings.cache_db_path),
            codex_config_path=str(CODEX_CONFIG_FILE),
            codex_configured=CODEX_CONFIG_FILE.exists() and "[mcp_servers.research]" in CODEX_CONFIG_FILE.read_text(encoding="utf-8", errors="ignore"),
            install_state_path=str(INSTALL_STATE_FILE),
            install_profile=install_state.install_profile,
            runtime_python=install_state.runtime_python,
            local_model_env_ready=local_env_python.exists(),
            local_model_profile=install_state.local_models.profile,
            available_tools=[
                "search_literature",
                "search_biomed",
                "search_source",
                "resolve_open_access",
                "health_check",
                "download_pdfs",
                "organize_library",
                "collect_library",
                "import_library",
                "list_libraries",
                "read_library",
                "rename_library",
                "archive_library",
                "restore_library",
                "tag_library",
                "update_library_item",
                "archive_library_item",
                "restore_library_item",
                "generate_context_bundle",
                "read_context_bundle",
                "render_library_manager",
                "get_analysis_settings",
                "update_analysis_settings",
                "ingest_library",
                "ingest_library_item",
                "summarize_library",
                "summarize_library_item",
                "compare_library_items",
                "analyze_library_topic",
                "search_library_evidence",
                "build_research_synthesis",
                "read_synthesis_report",
                "list_analysis_reports",
                "read_analysis_report",
            ],
            provider_statuses=provider_statuses,
            suggestions=list(dict.fromkeys(suggestions)),
        )

    def _run_provider_group(
        self,
        *,
        query: str,
        provider_names: list[str],
        mode: str,
        limit: int,
        sort: str,
    ) -> SearchResponse:
        fetch_limit = min(max(limit * 2, limit), self.settings.max_results_per_provider)
        results = []
        coverage: list[ProviderCoverage] = []
        warnings: list[str] = []
        provider_names = [name for name in provider_names if name in self.providers]
        expanded_query = expand_search_query(query)
        provider_queries = [query] if expanded_query == query else [query, expanded_query]

        ready_provider_names: list[str] = []
        for provider_name in provider_names:
            provider = self.providers[provider_name]
            ready, message = provider.ready()
            if not ready:
                coverage.append(ProviderCoverage(provider=provider.name, status="skipped", message=message))
                warnings.append(f"{provider.name}: {message}")
                continue
            ready_provider_names.append(provider_name)

        max_workers = min(max(int(self.settings.max_provider_workers), 1), max(len(ready_provider_names), 1))
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="scibudy-provider")
        futures = {
            executor.submit(self._search_one_provider, provider_name, provider_queries, fetch_limit, sort): provider_name
            for provider_name in ready_provider_names
        }
        started_at = time.monotonic()
        pending = set(futures)
        wait_timeout = min(float(self.settings.search_total_timeout_sec), float(self.settings.provider_timeout_sec))
        try:
            for future in concurrent.futures.as_completed(futures, timeout=wait_timeout):
                pending.discard(future)
                provider_name = futures[future]
                provider = self.providers[provider_name]
                try:
                    batch, elapsed_ms = future.result(timeout=0)
                    coverage.append(ProviderCoverage(provider=provider.name, status="ok", result_count=len(batch), elapsed_ms=elapsed_ms))
                    results.extend(batch)
                except Exception as exc:  # noqa: BLE001
                    elapsed_ms = int((time.monotonic() - started_at) * 1000)
                    coverage.append(ProviderCoverage(provider=provider.name, status="error", message=str(exc), elapsed_ms=elapsed_ms))
                    warnings.append(f"{provider.name}: {exc}")
        except concurrent.futures.TimeoutError:
            pass
        finally:
            for future in pending:
                provider_name = futures[future]
                provider = self.providers[provider_name]
                elapsed_ms = int((time.monotonic() - started_at) * 1000)
                future.cancel()
                message = f"provider timed out after {wait_timeout:g}s"
                coverage.append(ProviderCoverage(provider=provider.name, status="error", message=message, elapsed_ms=elapsed_ms))
                warnings.append(f"{provider.name}: {message}")
            executor.shutdown(wait=False, cancel_futures=True)

        provider_order = {self.providers[name].name: index for index, name in enumerate(provider_names)}
        coverage.sort(key=lambda item: provider_order.get(item.provider, len(provider_order)))

        ranked = dedupe_and_rank(results, query=query, sort=sort, limit=limit)
        return SearchResponse(
            query=query,
            mode=mode,
            sort=sort,
            generated_at=now_utc_iso(),
            result_count=len(ranked),
            provider_coverage=coverage,
            warnings=warnings,
            results=ranked,
        )

    def _search_one_provider(self, provider_name: str, queries: list[str], limit: int, sort: str) -> tuple[list, int]:
        provider = self.providers[provider_name]
        started_at = time.monotonic()
        batch = []
        for query in queries:
            batch.extend(provider.search(query=query, limit=limit, sort=sort))
        elapsed_ms = int((time.monotonic() - started_at) * 1000)
        if elapsed_ms > int(self.settings.provider_timeout_sec * 1000):
            raise ProviderRequestError(f"provider exceeded timeout budget of {self.settings.provider_timeout_sec:g}s")
        return batch, elapsed_ms

    def _register_library(self, response: OrganizeLibraryResponse, results: list, *, name: str | None = None) -> str:
        root = Path(response.target_dir)
        items = []
        record_map = {record.rank: record for record in response.records if record.rank is not None}
        for index, result in enumerate(results, start=1):
            rank = int(result.extras.get("rank") or index)
            record = record_map.get(rank)
            items.append(
                {
                    "rank": rank,
                    "title": result.title or f"Item {rank}",
                    "source": result.source,
                    "year": result.year,
                    "authors": result.authors,
                    "doi": result.doi,
                    "landing_url": result.landing_url,
                    "pdf_url": result.pdf_url,
                    "open_access_url": result.open_access_url,
                    "local_pdf_path": record.local_pdf_path if record else None,
                    "download_status": record.status if record else None,
                    "category": str(result.extras.get("category") or result.extras.get("type") or ""),
                    "notes": str(result.extras.get("why_high_value") or result.extras.get("why") or ""),
                    "metadata_path": record.local_metadata_path if record else None,
                }
            )

        summary = self.catalog.upsert_library(
            name=name or root.name,
            source_kind=response.source_kind,
            source_ref=response.source_ref,
            root_path=response.target_dir,
            manifest_path=response.manifest_path,
            csv_path=response.csv_path,
            markdown_path=response.markdown_path,
            bibtex_path=response.bibtex_path,
            checklist_csv_path=response.download_checklist_csv_path,
            checklist_markdown_path=response.download_checklist_markdown_path,
            items=items,
            records=response.records,
        )
        return summary.id


def _validate_query(query: str) -> str:
    cleaned = query.strip()
    if not cleaned:
        raise ValueError("query must not be empty")
    return cleaned


def _validate_limit(limit: int) -> int:
    return min(max(int(limit), 1), 50)


def _validate_sort(sort: str) -> str:
    normalized = sort.strip().lower()
    if normalized not in {"relevance", "recent"}:
        raise ValueError("sort must be one of: relevance, recent")
    return normalized


@lru_cache(maxsize=1)
def get_service() -> ResearchService:
    return ResearchService()
