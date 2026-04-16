from __future__ import annotations

import json
import logging
import sys
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response

from research_mcp.models import (
    AnalysisReportDetailResponse,
    AnalysisSettingsResponse,
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
    SearchResponse,
)
from research_mcp.service import get_service
from research_mcp.settings import get_settings
from research_mcp.ui_bundle import UI_TEMPLATE_URI, load_asset, load_local_index_html, load_widget_html


settings = get_settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.ERROR),
    stream=sys.stderr,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

app = FastMCP(
    "research",
    instructions="Unified scholarly search and library-management MCP for Codex and ChatGPT Apps.",
    log_level=settings.log_level.upper(),
)

READ_ONLY_TOOL = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=True)
MUTATING_TOOL = ToolAnnotations(readOnlyHint=False, idempotentHint=False, destructiveHint=False, openWorldHint=False)
ARCHIVE_TOOL = ToolAnnotations(readOnlyHint=False, idempotentHint=True, destructiveHint=True, openWorldHint=False)
RENDER_TOOL_META = {
    "ui": {"resourceUri": UI_TEMPLATE_URI, "visibility": ["model", "app"]},
    "openai/outputTemplate": UI_TEMPLATE_URI,
    "openai/widgetAccessible": True,
    "openai/toolInvocation/invoking": "Opening library manager…",
    "openai/toolInvocation/invoked": "Library manager ready",
}


@app.tool(
    description="Unified literature search across multiple scholarly providers.",
    structured_output=True,
    annotations=READ_ONLY_TOOL,
)
def search_literature(query: str, mode: str = "general", limit: int = 10, sort: str = "relevance") -> SearchResponse:
    return get_service().search_literature(query=query, mode=mode, limit=limit, sort=sort)


@app.tool(
    description="Biomedical literature search shortcut using PubMed, Europe PMC, OpenAlex, DOAJ, and CORE.",
    structured_output=True,
    annotations=READ_ONLY_TOOL,
)
def search_biomed(query: str, limit: int = 10, sort: str = "relevance") -> SearchResponse:
    return get_service().search_biomed(query=query, limit=limit, sort=sort)


@app.tool(description="Search a single provider directly.", structured_output=True, annotations=READ_ONLY_TOOL)
def search_source(source: str, query: str, limit: int = 10, sort: str = "relevance") -> SearchResponse:
    return get_service().search_source(source=source, query=query, limit=limit, sort=sort)


@app.tool(
    description="Resolve open-access links for a DOI through Unpaywall.",
    structured_output=True,
    annotations=READ_ONLY_TOOL,
)
def resolve_open_access(doi: str) -> OpenAccessResponse:
    return get_service().resolve_open_access(doi=doi)


@app.tool(
    description="Show provider readiness, missing credentials, local UI readiness, and Codex integration status.",
    structured_output=True,
    annotations=READ_ONLY_TOOL,
)
def health_check() -> HealthCheckResponse:
    return get_service().health_check()


@app.tool(description="Download PDFs for papers from a saved run or CSV file into a local directory.", structured_output=True)
def download_pdfs(run_id: str = "latest", csv_path: str | None = None, target_dir: str | None = None, limit: int = 20) -> DownloadBatchResponse:
    return get_service().download_pdfs(run_id=run_id, csv_path=csv_path, target_dir=target_dir, limit=limit)


@app.tool(
    description="Organize a local paper library from a saved run or CSV, writing CSV/Markdown/BibTeX outputs, downloading PDFs by default when available, and preserving a manual download checklist for misses.",
    structured_output=True,
)
def organize_library(
    run_id: str = "latest",
    csv_path: str | None = None,
    target_dir: str | None = None,
    limit: int = 50,
    download_pdfs: bool = True,
    name: str | None = None,
) -> OrganizeLibraryResponse:
    return get_service().organize_library(
        run_id=run_id,
        csv_path=csv_path,
        target_dir=target_dir,
        limit=limit,
        download_pdfs=download_pdfs,
        name=name,
    )


@app.tool(
    description="Run a search and immediately organize the results into a local literature library, downloading PDFs by default when available and preserving rich manual download checklist data when downloads miss.",
    structured_output=True,
)
def collect_library(
    query: str,
    mode: str = "general",
    limit: int = 20,
    sort: str = "relevance",
    target_dir: str | None = None,
    download_pdfs: bool = True,
    name: str | None = None,
) -> OrganizeLibraryResponse:
    return get_service().collect_library(
        query=query,
        mode=mode,
        limit=limit,
        sort=sort,
        target_dir=target_dir,
        download_pdfs=download_pdfs,
        name=name,
    )


@app.tool(description="Import an existing organized library directory or CSV into the managed catalog.", structured_output=True, annotations=MUTATING_TOOL)
def import_library(path: str, name: str | None = None) -> LibraryMutationResponse:
    return get_service().import_library(path, name=name)


@app.tool(description="List managed libraries.", structured_output=True, annotations=READ_ONLY_TOOL)
def list_libraries(include_archived: bool = False) -> LibrariesResponse:
    return get_service().list_libraries(include_archived=include_archived)


@app.tool(description="Read one managed library including items and generated context bundles.", structured_output=True, annotations=READ_ONLY_TOOL)
def read_library(library_id: str, include_archived_items: bool = False) -> LibraryDetailResponse:
    return get_service().read_library(library_id, include_archived_items=include_archived_items)


@app.tool(description="Rename a managed library display name.", structured_output=True, annotations=MUTATING_TOOL)
def rename_library(library_id: str, new_name: str) -> LibraryMutationResponse:
    return get_service().rename_library(library_id, new_name)


@app.tool(description="Archive a library without permanently deleting its files.", structured_output=True, annotations=ARCHIVE_TOOL)
def archive_library(library_id: str) -> LibraryMutationResponse:
    return get_service().archive_library(library_id)


@app.tool(description="Restore an archived library.", structured_output=True, annotations=MUTATING_TOOL)
def restore_library(library_id: str) -> LibraryMutationResponse:
    return get_service().restore_library(library_id)


@app.tool(description="Attach tags to a managed library.", structured_output=True, annotations=MUTATING_TOOL)
def tag_library(library_id: str, tags: list[str]) -> LibraryMutationResponse:
    return get_service().tag_library(library_id, tags)


@app.tool(description="Update one managed library item with alias, notes, favorite flag, or tags.", structured_output=True, annotations=MUTATING_TOOL)
def update_library_item(
    item_id: str,
    title_alias: str | None = None,
    notes: str | None = None,
    favorite: bool | None = None,
    tags: list[str] | None = None,
) -> LibraryMutationResponse:
    return get_service().update_library_item(item_id, title_alias=title_alias, notes=notes, favorite=favorite, tags=tags)


@app.tool(description="Archive one library item without physically deleting files.", structured_output=True, annotations=ARCHIVE_TOOL)
def archive_library_item(item_id: str) -> LibraryMutationResponse:
    return get_service().archive_library_item(item_id)


@app.tool(description="Restore an archived library item.", structured_output=True, annotations=MUTATING_TOOL)
def restore_library_item(item_id: str) -> LibraryMutationResponse:
    return get_service().restore_library_item(item_id)


@app.tool(description="Generate a compact reusable context bundle from a managed library.", structured_output=True, annotations=MUTATING_TOOL)
def generate_context_bundle(
    library_id: str,
    name: str | None = None,
    mode: str = "compact",
    max_items: int = 12,
    favorites_only: bool = False,
) -> ContextBundleResponse:
    return get_service().generate_context_bundle(
        library_id,
        name=name,
        mode=mode,
        max_items=max_items,
        favorites_only=favorites_only,
    )


@app.tool(description="Read a previously generated context bundle.", structured_output=True, annotations=READ_ONLY_TOOL)
def read_context_bundle(bundle_id: str) -> ContextBundleResponse:
    return get_service().read_context_bundle(bundle_id)


@app.tool(description="Read the current global analysis settings and backend readiness.", structured_output=True, annotations=READ_ONLY_TOOL)
def get_analysis_settings() -> AnalysisSettingsResponse:
    return get_service().get_analysis_settings()


@app.tool(description="Update the global analysis settings stored for the research MCP.", structured_output=True, annotations=MUTATING_TOOL)
def update_analysis_settings(
    analysis_mode: str | None = None,
    compute_backend: str | None = None,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
    max_summary_depth: str | None = None,
    forum_enrichment_enabled: bool | None = None,
    forum_source_profile: str | None = None,
    forum_sources: list[str] | None = None,
    openai_embedding_model: str | None = None,
    openai_summary_model: str | None = None,
    local_embedding_model: str | None = None,
    local_embedding_dimension: int | None = None,
    local_embedding_env: str | None = None,
    local_reranker_model: str | None = None,
    local_reranker_env: str | None = None,
) -> AnalysisSettingsResponse:
    return get_service().update_analysis_settings(
        analysis_mode=analysis_mode,
        compute_backend=compute_backend,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        max_summary_depth=max_summary_depth,
        forum_enrichment_enabled=forum_enrichment_enabled,
        forum_source_profile=forum_source_profile,
        forum_sources=",".join(forum_sources) if forum_sources is not None else None,
        openai_embedding_model=openai_embedding_model,
        openai_summary_model=openai_summary_model,
        local_embedding_model=local_embedding_model,
        local_embedding_dimension=local_embedding_dimension,
        local_embedding_env=local_embedding_env,
        local_reranker_model=local_reranker_model,
        local_reranker_env=local_reranker_env,
    )


@app.tool(description="Ingest full text and optional forum evidence for a managed library.", structured_output=True, annotations=MUTATING_TOOL)
def ingest_library(library_id: str, include_forums: bool = True, reingest: bool = False) -> IngestResponse:
    return get_service().ingest_library(library_id, include_forums=include_forums, reingest=reingest)


@app.tool(description="Ingest full text and optional forum evidence for one managed library item.", structured_output=True, annotations=MUTATING_TOOL)
def ingest_library_item(item_id: str, include_forums: bool = True, reingest: bool = False) -> IngestResponse:
    return get_service().ingest_library_item(item_id, include_forums=include_forums, reingest=reingest)


@app.tool(description="Summarize an ingested managed library.", structured_output=True, annotations=READ_ONLY_TOOL)
def summarize_library(library_id: str, topic: str | None = None) -> AnalysisSummaryResponse:
    return get_service().summarize_library(library_id, topic=topic)


@app.tool(description="Summarize one ingested managed library item.", structured_output=True, annotations=READ_ONLY_TOOL)
def summarize_library_item(item_id: str, topic: str | None = None) -> AnalysisSummaryResponse:
    return get_service().summarize_library_item(item_id, topic=topic)


@app.tool(description="Compare multiple ingested library items.", structured_output=True, annotations=READ_ONLY_TOOL)
def compare_library_items(item_ids: list[str], topic: str | None = None) -> AnalysisSummaryResponse:
    return get_service().compare_library_items(item_ids, topic=topic)


@app.tool(description="Analyze an ingested library around a specific topic.", structured_output=True, annotations=READ_ONLY_TOOL)
def analyze_library_topic(library_id: str, topic: str) -> AnalysisSummaryResponse:
    return get_service().analyze_library_topic(library_id, topic)


@app.tool(description="Search an analyzed library's ingested evidence/chunks with lexical+semantic retrieval.", structured_output=True, annotations=READ_ONLY_TOOL)
def search_library_evidence(library_id: str, query: str, max_hits: int = 8) -> AnalysisSummaryResponse:
    return get_service().search_library_evidence(library_id, query, max_hits=max_hits)


@app.tool(description="Build a structured cross-paper synthesis with method cards, comparison matrix, calibration digest, and claim/evidence graph.", structured_output=True, annotations=READ_ONLY_TOOL)
def build_research_synthesis(library_id: str, topic: str, max_items: int = 50) -> AnalysisSummaryResponse:
    return get_service().build_research_synthesis(library_id=library_id, topic=topic, max_items=max_items)


@app.tool(description="Read one persisted structured synthesis report.", structured_output=True, annotations=READ_ONLY_TOOL)
def read_synthesis_report(report_id: str) -> AnalysisReportDetailResponse:
    return get_service().read_synthesis_report(report_id)


@app.tool(description="List persisted analysis reports.", structured_output=True, annotations=READ_ONLY_TOOL)
def list_analysis_reports(library_id: str | None = None, item_id: str | None = None) -> AnalysisReportsResponse:
    return get_service().list_analysis_reports(library_id=library_id, item_id=item_id)


@app.tool(description="Read one persisted analysis report.", structured_output=True, annotations=READ_ONLY_TOOL)
def read_analysis_report(report_id: str) -> AnalysisReportDetailResponse:
    return get_service().read_analysis_report(report_id)


@app.tool(
    name="render_library_manager",
    description="Use this when you want to open the library management UI in ChatGPT Apps or inspect the current library-manager bootstrap state.",
    annotations=READ_ONLY_TOOL,
    meta=RENDER_TOOL_META,
)
def render_library_manager(library_id: str | None = None, include_archived: bool = False) -> dict[str, Any]:
    return get_service().render_library_manager(library_id=library_id, include_archived=include_archived)


@app.resource(
    UI_TEMPLATE_URI,
    name="library-manager-widget",
    title="Research Library Manager",
    description="Interactive research library manager UI for ChatGPT Apps and local browser use.",
    mime_type="text/html;profile=mcp-app",
    meta={"version": "v1"},
)
def library_manager_widget() -> str:
    return load_widget_html()


@app.resource("research://libraries/summary", name="libraries-summary", title="Libraries Summary", description="Compact markdown summary of all managed libraries.", mime_type="text/markdown")
def libraries_summary_resource() -> str:
    libraries = get_service().list_libraries().libraries
    lines = ["# Libraries", ""]
    for library in libraries:
        lines.append(f"- {library.name} [{library.id}] ({library.active_item_count}/{library.item_count} active)")
    return "\n".join(lines)


@app.resource("research://library/{library_id}/summary", name="library-summary", title="Library Summary", description="Compact summary of one library suitable for context loading.", mime_type="text/markdown")
def library_summary_resource(library_id: str) -> str:
    return get_service().catalog.compact_summary_for_library(library_id)


@app.resource("research://library/{library_id}/items", name="library-items", title="Library Items", description="Markdown list of items in one library.", mime_type="text/markdown")
def library_items_resource(library_id: str) -> str:
    return get_service().catalog.library_items_markdown(library_id)


@app.resource("research://bundle/{bundle_id}", name="context-bundle", title="Context Bundle", description="Saved compact context bundle text.", mime_type="text/markdown")
def context_bundle_resource(bundle_id: str) -> str:
    response = get_service().read_context_bundle(bundle_id)
    return response.text or ""


@app.resource("research://report/{report_id}", name="analysis-report", title="Analysis Report", description="Saved analysis report text.", mime_type="text/markdown")
def analysis_report_resource(report_id: str) -> str:
    response = get_service().read_analysis_report(report_id)
    if response.status != "ok":
        return "Report not found."
    lines = [f"# {response.report.title}", "", response.summary or "", "", "## Key points"]
    for point in response.key_points:
        lines.append(f"- {point}")
    if response.evidence:
        lines.extend(["", "## Evidence"])
        for ev in response.evidence:
            lines.append(f"- [{ev.source_type}] {ev.title or ev.url or ev.excerpt or ''}")
    return "\n".join(lines)


@app.resource("research://library/{library_id}/reports", name="library-reports", title="Library Reports", description="Saved analysis reports for one library.", mime_type="text/markdown")
def library_reports_resource(library_id: str) -> str:
    response = get_service().list_analysis_reports(library_id=library_id)
    lines = ["# Library Reports", ""]
    for report in response.reports:
        topic = f" ({report.topic})" if report.topic else ""
        lines.append(f"- {report.analysis_kind}: {report.title}{topic} [{report.id}]")
    return "\n".join(lines)


@app.resource("research://item/{item_id}/reports", name="item-reports", title="Item Reports", description="Saved analysis reports for one item.", mime_type="text/markdown")
def item_reports_resource(item_id: str) -> str:
    response = get_service().list_analysis_reports(item_id=item_id)
    lines = ["# Item Reports", ""]
    for report in response.reports:
        topic = f" ({report.topic})" if report.topic else ""
        lines.append(f"- {report.analysis_kind}: {report.title}{topic} [{report.id}]")
    return "\n".join(lines)


@app.prompt(name="load_library_context", title="Load Library Context", description="Inject a compact library bundle into the current conversation.")
def load_library_context(library_id: str, max_items: int = 12) -> list[dict[str, Any]]:
    text = get_service().catalog.compact_summary_for_library(library_id, max_items=max_items)
    return [{"role": "user", "content": text}]


@app.prompt(name="load_context_bundle", title="Load Context Bundle", description="Inject a previously generated compact context bundle into the current conversation.")
def load_context_bundle(bundle_id: str) -> list[dict[str, Any]]:
    response = get_service().read_context_bundle(bundle_id)
    return [{"role": "user", "content": response.text or ""}]


@app.prompt(name="load_topic_context", title="Load Topic Context", description="Inject a topic-specific synthesized summary from an analyzed library.")
def load_topic_context(library_id: str, topic: str) -> list[dict[str, Any]]:
    response = get_service().analyze_library_topic(library_id, topic)
    return [{"role": "user", "content": response.summary}]


@app.prompt(name="load_analysis_report", title="Load Analysis Report", description="Inject a saved analysis report into the current conversation.")
def load_analysis_report(report_id: str) -> list[dict[str, Any]]:
    response = get_service().read_analysis_report(report_id)
    return [{"role": "user", "content": response.summary or response.message or "Report not found."}]


@app.prompt(name="load_item_report", title="Load Item Report", description="Inject the latest item-level report for a library item into the current conversation.")
def load_item_report(item_id: str) -> list[dict[str, Any]]:
    reports = get_service().list_analysis_reports(item_id=item_id).reports
    if not reports:
        return [{"role": "user", "content": "No reports found for this item."}]
    response = get_service().read_analysis_report(reports[0].id)
    return [{"role": "user", "content": response.summary or response.message or "Report not found."}]


@app.custom_route("/health", methods=["GET"], include_in_schema=False)
async def http_health(_request: Request) -> Response:
    payload = get_service().health_check().model_dump(mode="json")
    payload["ui_ready"] = True
    payload["analysis_settings"] = get_service().get_analysis_settings().model_dump(mode="json")
    return JSONResponse(payload)


@app.custom_route("/api/bootstrap", methods=["GET"], include_in_schema=False)
async def http_bootstrap(request: Request) -> Response:
    library_id = request.query_params.get("library_id")
    include_archived = request.query_params.get("include_archived", "false").lower() == "true"
    payload = get_service().get_ui_bootstrap(library_id=library_id, include_archived=include_archived).model_dump(mode="json")
    return JSONResponse(payload)


@app.custom_route("/api/tool/{tool_name:path}", methods=["POST"], include_in_schema=False)
async def http_tool(request: Request) -> Response:
    tool_name = request.path_params.get("tool_name", "")
    args = await request.json() if request.method == "POST" else {}
    payload = _invoke_local_tool(tool_name, args)
    return JSONResponse(payload)


@app.custom_route("/app", methods=["GET"], include_in_schema=False)
async def http_app_index(_request: Request) -> Response:
    return HTMLResponse(load_local_index_html())


@app.custom_route("/app/{path:path}", methods=["GET"], include_in_schema=False)
async def http_app_assets(request: Request) -> Response:
    path = request.path_params.get("path", "")
    if not path or path == "index.html":
        return HTMLResponse(load_local_index_html())
    try:
        body, mime_type = load_asset(path)
    except FileNotFoundError:
        return Response(status_code=404)
    return Response(body, media_type=mime_type)


def _invoke_local_tool(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    service = get_service()
    mapping = {
        "list_libraries": lambda: service.list_libraries(include_archived=bool(args.get("include_archived", False))),
        "read_library": lambda: service.read_library(args["library_id"], include_archived_items=bool(args.get("include_archived_items", False))),
        "rename_library": lambda: service.rename_library(args["library_id"], args["new_name"]),
        "archive_library": lambda: service.archive_library(args["library_id"]),
        "restore_library": lambda: service.restore_library(args["library_id"]),
        "tag_library": lambda: service.tag_library(args["library_id"], list(args.get("tags") or [])),
        "update_library_item": lambda: service.update_library_item(
            args["item_id"],
            title_alias=args.get("title_alias"),
            notes=args.get("notes"),
            favorite=args.get("favorite"),
            tags=args.get("tags"),
        ),
        "archive_library_item": lambda: service.archive_library_item(args["item_id"]),
        "restore_library_item": lambda: service.restore_library_item(args["item_id"]),
        "generate_context_bundle": lambda: service.generate_context_bundle(
            args["library_id"],
            name=args.get("name"),
            mode=args.get("mode", "compact"),
            max_items=int(args.get("max_items", 12)),
            favorites_only=bool(args.get("favorites_only", False)),
        ),
        "read_context_bundle": lambda: service.read_context_bundle(args["bundle_id"]),
        "import_library": lambda: service.import_library(args["path"], name=args.get("name")),
        "render_library_manager": lambda: service.render_library_manager(
            library_id=args.get("library_id"),
            include_archived=bool(args.get("include_archived", False)),
        ),
        "get_analysis_settings": lambda: service.get_analysis_settings(),
        "update_analysis_settings": lambda: service.update_analysis_settings(
            analysis_mode=args.get("analysis_mode"),
            compute_backend=args.get("compute_backend"),
            chunk_size=args.get("chunk_size"),
            chunk_overlap=args.get("chunk_overlap"),
            max_summary_depth=args.get("max_summary_depth"),
            forum_enrichment_enabled=args.get("forum_enrichment_enabled"),
            forum_source_profile=args.get("forum_source_profile"),
            forum_sources=",".join(args.get("forum_sources")) if args.get("forum_sources") else None,
            openai_embedding_model=args.get("openai_embedding_model"),
            openai_summary_model=args.get("openai_summary_model"),
            local_embedding_model=args.get("local_embedding_model"),
            local_embedding_dimension=args.get("local_embedding_dimension"),
            local_embedding_env=args.get("local_embedding_env"),
            local_reranker_model=args.get("local_reranker_model"),
            local_reranker_env=args.get("local_reranker_env"),
        ),
        "ingest_library": lambda: service.ingest_library(
            args["library_id"],
            include_forums=bool(args.get("include_forums", True)),
            reingest=bool(args.get("reingest", False)),
        ),
        "ingest_library_item": lambda: service.ingest_library_item(
            args["item_id"],
            include_forums=bool(args.get("include_forums", True)),
            reingest=bool(args.get("reingest", False)),
        ),
        "summarize_library": lambda: service.summarize_library(args["library_id"], topic=args.get("topic")),
        "summarize_library_item": lambda: service.summarize_library_item(args["item_id"], topic=args.get("topic")),
        "compare_library_items": lambda: service.compare_library_items(list(args.get("item_ids") or []), topic=args.get("topic")),
        "analyze_library_topic": lambda: service.analyze_library_topic(args["library_id"], args["topic"]),
        "search_library_evidence": lambda: service.search_library_evidence(args["library_id"], args["query"], max_hits=int(args.get("max_hits", 8))),
        "list_analysis_reports": lambda: service.list_analysis_reports(library_id=args.get("library_id"), item_id=args.get("item_id")),
        "read_analysis_report": lambda: service.read_analysis_report(args["report_id"]),
    }
    if tool_name not in mapping:
        return {"status": "error", "message": f"Unsupported tool: {tool_name}"}
    result = mapping[tool_name]()
    if hasattr(result, "model_dump"):
        return result.model_dump(mode="json")
    return result


def main(transport: str = "stdio", *, host: str | None = None, port: int | None = None, mount_path: str | None = None) -> None:
    if host:
        app.settings.host = host
    if port:
        app.settings.port = port
    app.run(transport=transport, mount_path=mount_path)
