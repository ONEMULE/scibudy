from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
import webbrowser
from pathlib import Path
from typing import Any

from dotenv import dotenv_values

from research_mcp import __version__
from research_mcp.codex_config import install_to_codex_config
from research_mcp.formatters import (
    format_analysis_settings_response,
    format_analysis_summary_response,
    format_ingest_response,
    format_context_bundle_response,
    format_download_batch_response,
    format_libraries_response,
    format_library_detail_response,
    format_mutation_response,
    format_open_access_response,
    format_organize_library_response,
    format_provider_statuses,
    format_run_list,
    format_search_response,
)
from research_mcp.install_state import load_install_state
from research_mcp.paths import CODEX_CONFIG_FILE, ENV_FILE
from research_mcp.release_manifest import load_release_manifest
from research_mcp.runtime_install import (
    bootstrap_runtime,
    bootstrap_summary,
    install_local_model_stack,
    supports_full_local_models,
    sync_ui_assets,
    uninstall_local_models,
    upgrade_runtime,
    warm_local_models,
)
from research_mcp.runstore import list_runs, load_run, save_run
from research_mcp.server import main as serve_main
from research_mcp.service import ResearchService
from research_mcp.skill_install import install_skill


SECRET_KEYS = {"OPENALEX_API_KEY", "SEMANTIC_SCHOLAR_API_KEY", "NCBI_API_KEY", "CORE_API_KEY", "OPENAI_API_KEY"}
KEY_SPECS = [
    ("OPENALEX_API_KEY", "OpenAlex API key", True),
    ("CROSSREF_MAILTO", "Crossref contact email", True),
    ("SEMANTIC_SCHOLAR_API_KEY", "Semantic Scholar API key", False),
    ("NCBI_API_KEY", "NCBI API key", False),
    ("UNPAYWALL_EMAIL", "Unpaywall email", True),
    ("CORE_API_KEY", "CORE API key", False),
    ("OPENAI_API_KEY", "OpenAI API key", False),
]
KEY_GROUP_LABELS = {
    True: "Strongly recommended keys",
    False: "Optional performance and coverage keys",
}


def mcp_main() -> None:
    if len(sys.argv) == 1:
        serve_main()
        return
    args = build_parser().parse_args()
    dispatch(args)


def cli_main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        return
    dispatch(args)


def dispatch(args: argparse.Namespace) -> None:
    if args.command == "version":
        print(f"Scibudy {__version__}")
    elif args.command == "serve":
        run_serve(args)
    elif args.command == "ui":
        run_ui(args)
    elif args.command == "setup":
        run_setup(args)
    elif args.command == "doctor":
        run_doctor(args)
    elif args.command == "bootstrap":
        run_bootstrap(args)
    elif args.command == "install-codex":
        print(f"Installed research MCP block into {install_to_codex_config()}")
    elif args.command == "search":
        run_search(args)
    elif args.command == "source":
        run_source(args)
    elif args.command == "oa":
        run_oa(args)
    elif args.command == "download":
        run_download(args)
    elif args.command == "organize":
        run_organize(args)
    elif args.command == "collect":
        run_collect(args)
    elif args.command == "providers":
        run_providers(args)
    elif args.command == "runs":
        run_runs(args)
    elif args.command == "show":
        run_show(args)
    elif args.command == "install-skill":
        run_install_skill(args)
    elif args.command == "import-library":
        run_import_library(args)
    elif args.command == "libraries":
        run_libraries(args)
    elif args.command == "library-show":
        run_library_show(args)
    elif args.command == "bundle-create":
        run_bundle_create(args)
    elif args.command == "bundle-show":
        run_bundle_show(args)
    elif args.command == "analysis-settings":
        run_analysis_settings(args)
    elif args.command == "analysis-update":
        run_analysis_update(args)
    elif args.command == "ingest-library":
        run_ingest_library(args)
    elif args.command == "ingest-item":
        run_ingest_item(args)
    elif args.command == "summarize-library":
        run_summarize_library(args)
    elif args.command == "summarize-item":
        run_summarize_item(args)
    elif args.command == "compare-items":
        run_compare_items(args)
    elif args.command == "analyze-topic":
        run_analyze_topic(args)
    elif args.command == "search-evidence":
        run_search_evidence(args)
    elif args.command == "synthesize-library":
        run_synthesize_library(args)
    elif args.command == "analysis-reports":
        run_analysis_reports(args)
    elif args.command == "analysis-report-show":
        run_analysis_report_show(args)
    elif args.command == "install-local-models":
        run_install_local_models(args)
    elif args.command == "warm-local-models":
        run_warm_local_models(args)
    elif args.command == "uninstall-local-models":
        run_uninstall_local_models(args)
    elif args.command == "show-install-state":
        run_show_install_state(args)
    elif args.command == "upgrade-runtime":
        run_upgrade_runtime(args)
    else:
        raise SystemExit(2)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="scibudy")
    parser.add_argument("--version", action="version", version=f"Scibudy {__version__}")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("version", help="Print the Scibudy version.")

    serve_parser = subparsers.add_parser("serve", help="Run the MCP server.")
    serve_parser.add_argument("--transport", choices=["stdio", "sse", "streamable-http"], default="stdio")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8000)

    ui_parser = subparsers.add_parser("ui", help="Run the local browser management UI.")
    ui_parser.add_argument("--host", default="127.0.0.1")
    ui_parser.add_argument("--port", type=int, default=8765)
    ui_parser.add_argument("--open", action="store_true", help="Open the browser automatically.")

    setup_parser = subparsers.add_parser("setup", help="Create or update the local .env secrets file.")
    setup_parser.add_argument("--set", action="append", default=[], metavar="KEY=VALUE")
    setup_parser.add_argument("--clear", action="append", default=[], metavar="KEY")
    setup_parser.add_argument("--no-prompt", action="store_true")
    setup_parser.add_argument("--install-codex", action="store_true")

    doctor_parser = subparsers.add_parser("doctor", help="Show setup status and optional smoke results.")
    doctor_parser.add_argument("--json", action="store_true")
    doctor_parser.add_argument("--smoke", action="store_true")

    bootstrap_parser = subparsers.add_parser("bootstrap", help="Run the unified first-time bootstrap flow.")
    bootstrap_parser.add_argument("--profile", choices=["base", "analysis", "gpu-local", "full"], default="base")
    bootstrap_parser.add_argument("--install-codex", dest="install_codex", action="store_true", default=None)
    bootstrap_parser.add_argument("--no-install-codex", dest="install_codex", action="store_false")
    bootstrap_parser.add_argument("--no-prompt", action="store_true")
    bootstrap_parser.add_argument("--skip-doctor", action="store_true")
    bootstrap_parser.add_argument("--skip-warm-models", action="store_true")
    bootstrap_parser.add_argument("--format", choices=["table", "json"], default="table")

    subparsers.add_parser("install-codex", help="Install or update the managed Codex MCP config block.")

    search_parser = subparsers.add_parser("search", help="Search literature across one of the high-level modes.")
    search_parser.add_argument("query", nargs="+")
    search_parser.add_argument("--mode", choices=["general", "preprint", "biomed"], default="general")
    search_parser.add_argument("--limit", type=int, default=10)
    search_parser.add_argument("--sort", choices=["relevance", "recent"], default="relevance")
    search_parser.add_argument("--format", choices=["table", "json", "markdown", "titles", "tsv"], default="table")
    search_parser.add_argument("--details", action="store_true")
    search_parser.add_argument("--save", action="store_true")

    source_parser = subparsers.add_parser("source", help="Search a single provider directly.")
    source_parser.add_argument("source", choices=["arxiv", "openalex", "crossref", "semanticscholar", "pubmed", "europepmc", "doaj", "core"])
    source_parser.add_argument("query", nargs="+")
    source_parser.add_argument("--limit", type=int, default=10)
    source_parser.add_argument("--sort", choices=["relevance", "recent"], default="relevance")
    source_parser.add_argument("--format", choices=["table", "json", "markdown", "titles", "tsv"], default="table")
    source_parser.add_argument("--details", action="store_true")
    source_parser.add_argument("--save", action="store_true")

    oa_parser = subparsers.add_parser("oa", help="Resolve open-access links for a DOI.")
    oa_parser.add_argument("doi")
    oa_parser.add_argument("--format", choices=["table", "json"], default="table")
    oa_parser.add_argument("--save", action="store_true")

    download_parser = subparsers.add_parser("download", help="Download PDFs from a saved run or CSV file.")
    download_parser.add_argument("--run-id", default="latest")
    download_parser.add_argument("--csv", dest="csv_path")
    download_parser.add_argument("--target-dir", required=True)
    download_parser.add_argument("--limit", type=int, default=20)
    download_parser.add_argument("--format", choices=["table", "json"], default="table")

    organize_parser = subparsers.add_parser("organize", help="Organize a paper library from a saved run or CSV file.")
    organize_parser.add_argument("--run-id", default="latest")
    organize_parser.add_argument("--csv", dest="csv_path")
    organize_parser.add_argument("--target-dir", required=True)
    organize_parser.add_argument("--limit", type=int, default=50)
    organize_parser.add_argument("--download-pdfs", action="store_true", help="Explicit alias for the default behavior.")
    organize_parser.add_argument("--skip-pdfs", action="store_true")
    organize_parser.add_argument("--name")
    organize_parser.add_argument("--format", choices=["table", "json"], default="table")

    collect_parser = subparsers.add_parser("collect", help="Search and organize a paper library in one step.")
    collect_parser.add_argument("query", nargs="+")
    collect_parser.add_argument("--mode", choices=["general", "preprint", "biomed"], default="general")
    collect_parser.add_argument("--limit", type=int, default=20)
    collect_parser.add_argument("--sort", choices=["relevance", "recent"], default="relevance")
    collect_parser.add_argument("--target-dir", required=True)
    collect_parser.add_argument("--download-pdfs", action="store_true", help="Explicit alias for the default behavior.")
    collect_parser.add_argument("--skip-pdfs", action="store_true")
    collect_parser.add_argument("--name")
    collect_parser.add_argument("--format", choices=["table", "json"], default="table")

    providers_parser = subparsers.add_parser("providers", help="Show provider readiness and missing credentials.")
    providers_parser.add_argument("--format", choices=["table", "json"], default="table")

    runs_parser = subparsers.add_parser("runs", help="List saved CLI runs.")
    runs_parser.add_argument("--limit", type=int, default=20)
    runs_parser.add_argument("--format", choices=["table", "json"], default="table")

    show_parser = subparsers.add_parser("show", help="Show a saved run by id, path, or 'latest'.")
    show_parser.add_argument("run_id")
    show_parser.add_argument("--format", choices=["table", "json", "markdown", "titles", "tsv"], default="table")
    show_parser.add_argument("--details", action="store_true")

    subparsers.add_parser("install-skill", help="Install the Codex skill for this toolchain.")

    import_parser = subparsers.add_parser("import-library", help="Import an existing organized library into the management catalog.")
    import_parser.add_argument("path")
    import_parser.add_argument("--name")
    import_parser.add_argument("--format", choices=["table", "json"], default="table")

    libraries_parser = subparsers.add_parser("libraries", help="List managed libraries.")
    libraries_parser.add_argument("--include-archived", action="store_true")
    libraries_parser.add_argument("--format", choices=["table", "json"], default="table")

    library_show_parser = subparsers.add_parser("library-show", help="Show one managed library with items and bundles.")
    library_show_parser.add_argument("library_id")
    library_show_parser.add_argument("--include-archived-items", action="store_true")
    library_show_parser.add_argument("--format", choices=["table", "json"], default="table")

    bundle_create_parser = subparsers.add_parser("bundle-create", help="Generate a compact context bundle from a library.")
    bundle_create_parser.add_argument("library_id")
    bundle_create_parser.add_argument("--name")
    bundle_create_parser.add_argument("--mode", choices=["compact", "medium"], default="compact")
    bundle_create_parser.add_argument("--max-items", type=int, default=12)
    bundle_create_parser.add_argument("--favorites-only", action="store_true")
    bundle_create_parser.add_argument("--format", choices=["table", "json"], default="table")

    bundle_show_parser = subparsers.add_parser("bundle-show", help="Show one generated context bundle.")
    bundle_show_parser.add_argument("bundle_id")
    bundle_show_parser.add_argument("--format", choices=["table", "json"], default="table")

    analysis_settings_parser = subparsers.add_parser("analysis-settings", help="Show current analysis settings.")
    analysis_settings_parser.add_argument("--format", choices=["table", "json"], default="table")

    analysis_update_parser = subparsers.add_parser("analysis-update", help="Update global analysis settings.")
    analysis_update_parser.add_argument("--analysis-mode", choices=["rules", "hybrid", "semantic_heavy"])
    analysis_update_parser.add_argument("--compute-backend", choices=["auto", "local", "openai"])
    analysis_update_parser.add_argument("--chunk-size", type=int)
    analysis_update_parser.add_argument("--chunk-overlap", type=int)
    analysis_update_parser.add_argument("--max-summary-depth", choices=["shallow", "standard", "deep"])
    analysis_update_parser.add_argument("--forum-enrichment-enabled", choices=["true", "false"])
    analysis_update_parser.add_argument("--forum-source-profile", choices=["high_trust", "extended", "experimental"])
    analysis_update_parser.add_argument("--forum-sources")
    analysis_update_parser.add_argument("--openai-embedding-model")
    analysis_update_parser.add_argument("--openai-summary-model")
    analysis_update_parser.add_argument("--local-embedding-model")
    analysis_update_parser.add_argument("--local-embedding-dimension", type=int)
    analysis_update_parser.add_argument("--local-embedding-env")
    analysis_update_parser.add_argument("--local-reranker-model")
    analysis_update_parser.add_argument("--local-reranker-env")
    analysis_update_parser.add_argument("--format", choices=["table", "json"], default="table")

    ingest_library_parser = subparsers.add_parser("ingest-library", help="Extract full text and optional forum evidence for a library.")
    ingest_library_parser.add_argument("library_id")
    ingest_library_parser.add_argument("--skip-forums", action="store_true")
    ingest_library_parser.add_argument("--reingest", action="store_true")
    ingest_library_parser.add_argument("--format", choices=["table", "json"], default="table")

    ingest_item_parser = subparsers.add_parser("ingest-item", help="Extract full text and optional forum evidence for one item.")
    ingest_item_parser.add_argument("item_id")
    ingest_item_parser.add_argument("--skip-forums", action="store_true")
    ingest_item_parser.add_argument("--reingest", action="store_true")
    ingest_item_parser.add_argument("--format", choices=["table", "json"], default="table")

    summarize_library_parser = subparsers.add_parser("summarize-library", help="Summarize an ingested library.")
    summarize_library_parser.add_argument("library_id")
    summarize_library_parser.add_argument("--topic")
    summarize_library_parser.add_argument("--format", choices=["table", "json"], default="table")

    summarize_item_parser = subparsers.add_parser("summarize-item", help="Summarize one ingested item.")
    summarize_item_parser.add_argument("item_id")
    summarize_item_parser.add_argument("--topic")
    summarize_item_parser.add_argument("--format", choices=["table", "json"], default="table")

    compare_items_parser = subparsers.add_parser("compare-items", help="Compare multiple ingested items.")
    compare_items_parser.add_argument("item_ids", nargs="+")
    compare_items_parser.add_argument("--topic")
    compare_items_parser.add_argument("--format", choices=["table", "json"], default="table")

    analyze_topic_parser = subparsers.add_parser("analyze-topic", help="Analyze one library around a topic.")
    analyze_topic_parser.add_argument("library_id")
    analyze_topic_parser.add_argument("topic")
    analyze_topic_parser.add_argument("--format", choices=["table", "json"], default="table")

    evidence_parser = subparsers.add_parser("search-evidence", help="Search analyzed library chunks/evidence.")
    evidence_parser.add_argument("library_id")
    evidence_parser.add_argument("query")
    evidence_parser.add_argument("--max-hits", type=int, default=8)
    evidence_parser.add_argument("--format", choices=["table", "json"], default="table")

    synthesize_parser = subparsers.add_parser("synthesize-library", help="Build a structured cross-paper synthesis report for an ingested library.")
    synthesize_parser.add_argument("library_id")
    synthesize_parser.add_argument("topic")
    synthesize_parser.add_argument("--max-items", type=int, default=50)
    synthesize_parser.add_argument("--format", choices=["table", "json"], default="table")

    reports_parser = subparsers.add_parser("analysis-reports", help="List persisted analysis reports.")
    reports_parser.add_argument("--library-id")
    reports_parser.add_argument("--item-id")
    reports_parser.add_argument("--format", choices=["table", "json"], default="table")

    report_show_parser = subparsers.add_parser("analysis-report-show", help="Show one persisted analysis report.")
    report_show_parser.add_argument("report_id")
    report_show_parser.add_argument("--format", choices=["table", "json"], default="table")

    install_local_models_parser = subparsers.add_parser("install-local-models", help="Create and populate the dedicated local GPU model environment.")
    install_local_models_parser.add_argument("--force", action="store_true")
    install_local_models_parser.add_argument("--skip-warm", action="store_true")
    install_local_models_parser.add_argument("--background-warm", action="store_true")
    install_local_models_parser.add_argument("--format", choices=["table", "json"], default="table")

    warm_local_models_parser = subparsers.add_parser("warm-local-models", help="Warm the local embedding and reranker model caches.")
    warm_local_models_parser.add_argument("--skip-embedding", action="store_true")
    warm_local_models_parser.add_argument("--skip-reranker", action="store_true")
    warm_local_models_parser.add_argument("--background", action="store_true")
    warm_local_models_parser.add_argument("--format", choices=["table", "json"], default="table")

    uninstall_local_models_parser = subparsers.add_parser("uninstall-local-models", help="Remove the dedicated local GPU model environment.")
    uninstall_local_models_parser.add_argument("--yes", action="store_true")
    uninstall_local_models_parser.add_argument("--format", choices=["table", "json"], default="table")

    install_state_parser = subparsers.add_parser("show-install-state", help="Show persisted install/bootstrap state.")
    install_state_parser.add_argument("--format", choices=["table", "json"], default="table")

    upgrade_runtime_parser = subparsers.add_parser("upgrade-runtime", help="Upgrade the installed Python runtime package.")
    upgrade_runtime_parser.add_argument("--spec")
    upgrade_runtime_parser.add_argument("--from-path")
    upgrade_runtime_parser.add_argument("--install-codex", action="store_true")
    upgrade_runtime_parser.add_argument("--format", choices=["table", "json"], default="table")

    return parser


def run_serve(args: argparse.Namespace) -> None:
    serve_main(transport=args.transport, host=args.host, port=args.port)


def run_ui(args: argparse.Namespace) -> None:
    url = f"http://{args.host}:{args.port}/app"
    if args.open:
        webbrowser.open(url)
    print(f"Library manager: {url}")
    serve_main(transport="streamable-http", host=args.host, port=args.port)


def apply_setup(
    *,
    set_items: list[str],
    clear_items: list[str],
    no_prompt: bool,
    install_codex: bool,
) -> dict[str, Any]:
    current = dict(dotenv_values(ENV_FILE))
    updates = parse_set_args(set_items)
    for key in clear_items:
        validate_key_name(key)
        updates[key] = ""
    if not no_prompt:
        print(f"Configuring research MCP secrets in {ENV_FILE}")
        print("Press Enter to keep the current value. Type '-' to clear a saved value.")
        for recommended in [True, False]:
            print("")
            print(KEY_GROUP_LABELS[recommended])
            for key, label, is_recommended in KEY_SPECS:
                if is_recommended != recommended or key in updates:
                    continue
                existing = (current.get(key) or "").strip()
                prompt = f"{label}"
                prompt += " (recommended)" if recommended else " (optional)"
                prompt += ": "
                value = prompt_for_value(key=key, prompt=prompt, existing=existing)
                if value is not None:
                    updates[key] = value
    merged = {key: value for key, value in current.items() if value}
    for key, value in updates.items():
        if value:
            merged[key] = value
        else:
            merged.pop(key, None)
    write_env_file(merged)
    installed_path = install_to_codex_config() if install_codex else None
    return {"env_file": str(ENV_FILE), "codex_config_path": str(installed_path) if installed_path else None}


def run_setup(args: argparse.Namespace) -> None:
    result = apply_setup(set_items=args.set, clear_items=args.clear, no_prompt=args.no_prompt, install_codex=args.install_codex)
    if result["codex_config_path"]:
        print(f"Updated Codex MCP config: {result['codex_config_path']}")
    print(f"Wrote {ENV_FILE}")


def run_doctor(args: argparse.Namespace) -> None:
    service = ResearchService()
    health = service.health_check()
    payload: dict[str, Any] = health.model_dump(mode="json")
    if args.smoke:
        payload["smoke"] = run_smoke_tests(service)
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    print(f"Research MCP {health.version}")
    print(f"Project root: {health.project_root}")
    if health.app_home:
        print(f"App home: {health.app_home}")
    if health.install_profile:
        print(f"Install profile: {health.install_profile}")
    if health.runtime_python:
        print(f"Runtime Python: {health.runtime_python}")
    print(f".env file: {health.env_file} ({'present' if health.env_file_exists else 'missing'})")
    print(f"Codex config: {health.codex_config_path} ({'configured' if health.codex_configured else 'missing research block'})")
    print(f"Cache DB: {health.cache_db_path}")
    if health.local_model_env_ready is not None:
        print(f"Local model env ready: {'yes' if health.local_model_env_ready else 'no'}")
    if health.local_model_profile:
        print(f"Local model profile: {health.local_model_profile}")
    print(f"Status: {health.status}")
    print("Providers:")
    for item in health.provider_statuses:
        state = "ready" if item.ready else "not ready"
        enabled = "enabled" if item.enabled else "disabled"
        detail = item.message or (f"missing {', '.join(item.missing_credentials)}" if item.missing_credentials else "")
        print(f"- {item.provider}: {enabled}, {state}" + (f" ({detail})" if detail else ""))
    if payload.get("smoke"):
        print("Smoke tests:")
        for item in payload["smoke"]:
            detail = f"count={item['result_count']}" if item["status"] == "ok" and "result_count" in item else item.get("message", "")
            print(f"- {item['provider']}: {item['status']} ({detail})")
    if health.suggestions:
        print("Recommended next steps:")
        for suggestion in health.suggestions:
            print(f"- {suggestion}")


def run_bootstrap(args: argparse.Namespace) -> None:
    manifest = load_release_manifest()
    install_codex = manifest.install_profiles[args.profile].get("codex", False) if args.install_codex is None else bool(args.install_codex)
    apply_setup(set_items=[], clear_items=[], no_prompt=args.no_prompt, install_codex=install_codex)
    settings = ResearchService().settings
    state = bootstrap_runtime(
        profile=args.profile,
        settings=settings,
        configure_secrets=not args.no_prompt,
        install_codex=install_codex,
        run_doctor=not args.skip_doctor,
        warm_models_now=not args.skip_warm_models and manifest.install_profiles[args.profile].get("warm_local_models", False),
    )
    if args.format == "json":
        payload = state.model_dump(mode="json")
        if not args.skip_doctor:
            payload["doctor"] = ResearchService().health_check().model_dump(mode="json")
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    print(bootstrap_summary(state))
    if not args.skip_doctor:
        print("")
        run_doctor(argparse.Namespace(json=False, smoke=False))


def run_search(args: argparse.Namespace) -> None:
    service = ResearchService()
    query = " ".join(args.query).strip()
    response = service.search_literature(query=query, mode=args.mode, limit=args.limit, sort=args.sort)
    payload = response.model_dump(mode="json")
    if args.save:
        path = save_run("search", payload, summary={"query": query, "mode": args.mode, "sort": args.sort, "result_count": response.result_count})
        print(f"Saved run: {path}", file=sys.stderr)
    print(format_search_response(payload, fmt=args.format, details=args.details))


def run_source(args: argparse.Namespace) -> None:
    service = ResearchService()
    query = " ".join(args.query).strip()
    response = service.search_source(source=args.source, query=query, limit=args.limit, sort=args.sort)
    payload = response.model_dump(mode="json")
    if args.save:
        path = save_run("source", payload, summary={"query": query, "source": args.source, "sort": args.sort, "result_count": response.result_count})
        print(f"Saved run: {path}", file=sys.stderr)
    print(format_search_response(payload, fmt=args.format, details=args.details))


def run_oa(args: argparse.Namespace) -> None:
    service = ResearchService()
    response = service.resolve_open_access(args.doi)
    payload = response.model_dump(mode="json")
    if args.save:
        path = save_run("oa", payload, summary={"doi": response.doi, "result_count": 1 if response.status == "ok" else 0})
        print(f"Saved run: {path}", file=sys.stderr)
    print(format_open_access_response(payload, fmt=args.format))


def run_download(args: argparse.Namespace) -> None:
    response = ResearchService().download_pdfs(run_id=args.run_id, csv_path=args.csv_path, target_dir=args.target_dir, limit=args.limit)
    print(format_download_batch_response(response.model_dump(mode="json"), fmt=args.format))


def run_organize(args: argparse.Namespace) -> None:
    response = ResearchService().organize_library(
        run_id=args.run_id,
        csv_path=args.csv_path,
        target_dir=args.target_dir,
        limit=args.limit,
        download_pdfs=not args.skip_pdfs,
        name=args.name,
    )
    print(format_organize_library_response(response.model_dump(mode="json"), fmt=args.format))


def run_collect(args: argparse.Namespace) -> None:
    query = " ".join(args.query).strip()
    response = ResearchService().collect_library(
        query=query,
        mode=args.mode,
        limit=args.limit,
        sort=args.sort,
        target_dir=args.target_dir,
        download_pdfs=not args.skip_pdfs,
        name=args.name,
    )
    print(format_organize_library_response(response.model_dump(mode="json"), fmt=args.format))


def run_providers(args: argparse.Namespace) -> None:
    print(format_provider_statuses(ResearchService().health_check().model_dump(mode="json"), fmt=args.format))


def run_runs(args: argparse.Namespace) -> None:
    print(format_run_list(list_runs(limit=args.limit), fmt=args.format))


def run_show(args: argparse.Namespace) -> None:
    document = load_run(args.run_id)
    kind = document.get("kind")
    payload = document.get("payload") or {}
    if args.format == "json":
        print(json.dumps(document, indent=2, ensure_ascii=False))
        return
    if kind in {"search", "source"}:
        print(format_search_response(payload, fmt=args.format, details=args.details))
    elif kind == "oa":
        print(format_open_access_response(payload, fmt="table"))
    else:
        print(json.dumps(document, indent=2, ensure_ascii=False))


def run_install_skill(_args: argparse.Namespace) -> None:
    print(f"Installed skill: {install_skill()}")


def run_import_library(args: argparse.Namespace) -> None:
    response = ResearchService().import_library(args.path, name=args.name)
    print(format_mutation_response(response.model_dump(mode="json"), fmt=args.format))


def run_libraries(args: argparse.Namespace) -> None:
    response = ResearchService().list_libraries(include_archived=args.include_archived)
    print(format_libraries_response(response.model_dump(mode="json"), fmt=args.format))


def run_library_show(args: argparse.Namespace) -> None:
    response = ResearchService().read_library(args.library_id, include_archived_items=args.include_archived_items)
    print(format_library_detail_response(response.model_dump(mode="json"), fmt=args.format))


def run_bundle_create(args: argparse.Namespace) -> None:
    response = ResearchService().generate_context_bundle(
        args.library_id,
        name=args.name,
        mode=args.mode,
        max_items=args.max_items,
        favorites_only=args.favorites_only,
    )
    print(format_context_bundle_response(response.model_dump(mode="json"), fmt=args.format))


def run_bundle_show(args: argparse.Namespace) -> None:
    response = ResearchService().read_context_bundle(args.bundle_id)
    print(format_context_bundle_response(response.model_dump(mode="json"), fmt=args.format))


def run_analysis_settings(args: argparse.Namespace) -> None:
    response = ResearchService().get_analysis_settings()
    print(format_analysis_settings_response(response.model_dump(mode="json"), fmt=args.format))


def run_analysis_update(args: argparse.Namespace) -> None:
    response = ResearchService().update_analysis_settings(
        analysis_mode=args.analysis_mode,
        compute_backend=args.compute_backend,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
        max_summary_depth=args.max_summary_depth,
        forum_enrichment_enabled=None if args.forum_enrichment_enabled is None else args.forum_enrichment_enabled == "true",
        forum_source_profile=args.forum_source_profile,
        forum_sources=args.forum_sources,
        openai_embedding_model=args.openai_embedding_model,
        openai_summary_model=args.openai_summary_model,
        local_embedding_model=args.local_embedding_model,
        local_embedding_dimension=args.local_embedding_dimension,
        local_embedding_env=args.local_embedding_env,
        local_reranker_model=args.local_reranker_model,
        local_reranker_env=args.local_reranker_env,
    )
    print(format_analysis_settings_response(response.model_dump(mode="json"), fmt=args.format))


def run_ingest_library(args: argparse.Namespace) -> None:
    response = ResearchService().ingest_library(args.library_id, include_forums=not args.skip_forums, reingest=args.reingest)
    print(format_ingest_response(response.model_dump(mode="json"), fmt=args.format))


def run_ingest_item(args: argparse.Namespace) -> None:
    response = ResearchService().ingest_library_item(args.item_id, include_forums=not args.skip_forums, reingest=args.reingest)
    print(format_ingest_response(response.model_dump(mode="json"), fmt=args.format))


def run_summarize_library(args: argparse.Namespace) -> None:
    response = ResearchService().summarize_library(args.library_id, topic=args.topic)
    print(format_analysis_summary_response(response.model_dump(mode="json"), fmt=args.format))


def run_summarize_item(args: argparse.Namespace) -> None:
    response = ResearchService().summarize_library_item(args.item_id, topic=args.topic)
    print(format_analysis_summary_response(response.model_dump(mode="json"), fmt=args.format))


def run_compare_items(args: argparse.Namespace) -> None:
    response = ResearchService().compare_library_items(args.item_ids, topic=args.topic)
    print(format_analysis_summary_response(response.model_dump(mode="json"), fmt=args.format))


def run_analyze_topic(args: argparse.Namespace) -> None:
    response = ResearchService().analyze_library_topic(args.library_id, args.topic)
    print(format_analysis_summary_response(response.model_dump(mode="json"), fmt=args.format))


def run_search_evidence(args: argparse.Namespace) -> None:
    response = ResearchService().search_library_evidence(args.library_id, args.query, max_hits=args.max_hits)
    print(format_analysis_summary_response(response.model_dump(mode="json"), fmt=args.format))


def run_synthesize_library(args: argparse.Namespace) -> None:
    response = ResearchService().build_research_synthesis(args.library_id, args.topic, max_items=args.max_items)
    print(format_analysis_summary_response(response.model_dump(mode="json"), fmt=args.format))


def run_analysis_reports(args: argparse.Namespace) -> None:
    response = ResearchService().list_analysis_reports(library_id=args.library_id, item_id=args.item_id)
    payload = response.model_dump(mode="json")
    if args.format == "json":
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        reports = payload.get("reports") or []
        if not reports:
            print("No analysis reports.")
            return
        headers = ["ID", "Kind", "Topic", "Title", "Backend", "Path"]
        rows = [[r.get("id",""), r.get("analysis_kind",""), r.get("topic",""), r.get("title",""), r.get("compute_backend",""), r.get("report_path","")] for r in reports]
        widths = [max(len(h), *(len(str(row[i])) for row in rows)) for i, h in enumerate(headers)]
        print("  ".join(h.ljust(widths[i]) for i, h in enumerate(headers)))
        print("  ".join("-"*widths[i] for i in range(len(headers))))
        for row in rows:
            print("  ".join(str(row[i]).ljust(widths[i]) for i in range(len(headers))))


def run_analysis_report_show(args: argparse.Namespace) -> None:
    response = ResearchService().read_analysis_report(args.report_id)
    payload = response.model_dump(mode="json")
    if args.format == "json":
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(format_analysis_summary_response(
            {
                "status": payload.get("status"),
                "title": (payload.get("report") or {}).get("title"),
                "analysis_mode": (payload.get("report") or {}).get("analysis_mode"),
                "compute_backend": (payload.get("report") or {}).get("compute_backend"),
                "topic": (payload.get("report") or {}).get("topic"),
                "summary": payload.get("summary"),
                "key_points": payload.get("key_points") or [],
                "evidence": payload.get("evidence") or [],
                "structured_payload": payload.get("structured_payload") or {},
            },
            fmt="table",
        ))


def run_install_local_models(args: argparse.Namespace) -> None:
    settings = ResearchService().settings
    if not supports_full_local_models():
        raise SystemExit("Full local model installation is currently supported only on Linux with NVIDIA GPUs.")
    env_python = install_local_model_stack(settings, force=args.force)
    warm_info: dict[str, Any] | None = None
    if not args.skip_warm:
        warm_info = warm_local_models(settings, background=args.background_warm)
    payload = {
        "status": "ok",
        "env_python": str(env_python),
        "embedding_model": settings.local_embedding_model,
        "reranker_model": settings.local_reranker_model,
        "warm": warm_info,
    }
    if args.format == "json":
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print("\n".join([f"{key}: {value}" for key, value in payload.items()]))


def run_warm_local_models(args: argparse.Namespace) -> None:
    settings = ResearchService().settings
    result = warm_local_models(
        settings,
        skip_embedding=args.skip_embedding,
        skip_reranker=args.skip_reranker,
        background=args.background,
    )
    if args.format == "json":
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print("\n".join([f"{key}: {value}" for key, value in result.items()]))


def run_uninstall_local_models(args: argparse.Namespace) -> None:
    if not args.yes:
        raise SystemExit("Pass --yes to remove the dedicated local model environment.")
    settings = ResearchService().settings
    uninstall_local_models(settings)
    payload = {"status": "ok", "env": settings.local_embedding_env}
    if args.format == "json":
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"Removed local model environment: {settings.local_embedding_env}")


def run_show_install_state(args: argparse.Namespace) -> None:
    state = load_install_state().model_dump(mode="json")
    if args.format == "json":
        print(json.dumps(state, indent=2, ensure_ascii=False))
        return
    lines = [
        f"version: {state.get('version')}",
        f"app_home: {state.get('app_home')}",
        f"platform: {state.get('platform')}",
        f"install_profile: {state.get('install_profile')}",
        f"runtime_python: {state.get('runtime_python')}",
        f"runtime_command: {state.get('runtime_command')}",
        f"codex_configured: {state.get('codex_configured')}",
        f"ui_assets_ready: {state.get('ui_assets_ready')}",
    ]
    local_models = state.get("local_models") or {}
    lines.extend(
        [
            f"local_models.profile: {local_models.get('profile')}",
            f"local_models.env_name: {local_models.get('env_name')}",
            f"local_models.installed: {local_models.get('installed')}",
            f"local_models.warmed_embedding: {local_models.get('warmed_embedding')}",
            f"local_models.warmed_reranker: {local_models.get('warmed_reranker')}",
        ]
    )
    print("\n".join(lines))


def run_upgrade_runtime(args: argparse.Namespace) -> None:
    manifest = load_release_manifest()
    if args.from_path:
        requirement = str(Path(args.from_path).expanduser().resolve())
    else:
        requirement = args.spec or manifest.python.requirement
    upgrade_runtime(requirement)
    if args.install_codex:
        install_to_codex_config()
    payload = {"status": "ok", "requirement": requirement}
    if args.format == "json":
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"Upgraded runtime using: {requirement}")


def parse_set_args(items: list[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise SystemExit(f"Invalid --set value: {item!r}. Expected KEY=VALUE.")
        key, value = item.split("=", 1)
        key = key.strip()
        validate_key_name(key)
        parsed[key] = value.strip()
    return parsed


def validate_key_name(key: str) -> None:
    if key not in {name for name, _, _ in KEY_SPECS}:
        raise SystemExit(f"Unsupported key: {key}")


def prompt_for_value(*, key: str, prompt: str, existing: str) -> str | None:
    if existing:
        prompt = f"{prompt}[saved: {mask_value(existing)}]"
    reader = getpass.getpass if key in SECRET_KEYS else input
    raw = reader(prompt)
    if raw == "":
        return existing
    if raw.strip() == "-":
        return ""
    return raw.strip()


def mask_value(value: str) -> str:
    if len(value) <= 8:
        return "****"
    return f"{value[:3]}...{value[-4:]}"


def write_env_file(values: dict[str, str]) -> None:
    ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Research MCP local secrets", "# Generated by: research-mcp setup", ""]
    for key, _, _ in KEY_SPECS:
        value = values.get(key, "")
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'{key}="{escaped}"')
    lines.append("")
    ENV_FILE.write_text("\n".join(lines), encoding="utf-8")
    try:
        os.chmod(ENV_FILE, 0o600)
    except OSError:
        pass


def run_smoke_tests(service: ResearchService) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = [
        {
            "provider": "Codex MCP config",
            "status": "ok" if CODEX_CONFIG_FILE.exists() and "[mcp_servers.research]" in CODEX_CONFIG_FILE.read_text(encoding="utf-8", errors="ignore") else "error",
            "message": str(CODEX_CONFIG_FILE),
        }
    ]
    queries = {
        "openalex": "test-time scaling multimodal reasoning",
        "arxiv": "diffusion model planning",
        "crossref": "test-time compute reasoning",
        "semanticscholar": "test-time compute reasoning",
        "pubmed": "CRISPR off-target prediction",
        "europepmc": "CRISPR off-target prediction",
        "doaj": "open access climate change",
        "core": "machine learning",
    }
    for source, provider in service.providers.items():
        ready, message = provider.ready()
        if not ready:
            checks.append({"provider": provider.name, "status": "skipped", "message": message})
            continue
        try:
            response = service.search_source(source=source, query=queries[source], limit=1)
            checks.append({"provider": provider.name, "status": "ok", "result_count": response.result_count})
        except Exception as exc:  # noqa: BLE001
            checks.append({"provider": provider.name, "status": "error", "message": str(exc)})
    return checks


if __name__ == "__main__":
    cli_main()
